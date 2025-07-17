use clap::Parser;
use postgres::{Client, NoTls, Statement};
use regex::Regex;
use std::collections::HashMap;
use std::env;
use std::fs;
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::path::Path;

const EMPTY_WORD: &str = "";
const EMPTY_WORD_ID: i32 = 1;
const BATCH_SIZE: usize = 10000;

#[derive(Parser)]
struct Args {
    /// Path to the text corpus file
    corpus_file: String,
}

fn get_pg_password() -> Option<String> {
    let primary = env::var("PG_PASSWORD_FILE").unwrap_or_else(|_| "./secrets/pg_password.txt".into());
    let candidates = [
        primary.clone(),
        format!("/run/secrets/{}", Path::new(&primary).file_name()?.to_string_lossy()),
        format!("{}/../secrets/{}", env!("CARGO_MANIFEST_DIR"), Path::new(&primary).file_name()?.to_string_lossy()),
    ];
    for path in candidates.iter() {
        if Path::new(path).exists() {
            return fs::read_to_string(path).ok().map(|s| s.trim().to_string());
        }
    }
    eprintln!("Password file not found at '{}' or fallback locations", primary);
    None
}

fn connect_db() -> Option<Client> {
    let password = match get_pg_password() {
        Some(p) => p,
        None => return None,
    };
    let host = env::var("PG_HOST").unwrap_or_else(|_| "localhost".into());
    let port = env::var("PG_PORT").unwrap_or_else(|_| "5432".into());
    let db = env::var("PG_DBNAME").unwrap_or_else(|_| "markovdb".into());
    let user = env::var("PG_USER").unwrap_or_else(|_| "markovuser".into());
    let conn_str = format!("host={} port={} dbname={} user={} password={}", host, port, db, user, password);
    match Client::connect(&conn_str, NoTls) {
        Ok(c) => Some(c),
        Err(e) => {
            eprintln!("ERROR: Failed to connect to PostgreSQL: {}", e);
            None
        }
    }
}

fn tokenize_text(text: &str, re_lt: &Regex, re_other: &Regex) -> Vec<String> {
    let tmp = re_lt.replace_all(text, "");
    let tmp2 = re_other.replace_all(&tmp, "");
    tmp2
        .to_lowercase()
        .split_whitespace()
        .filter(|w| !w.is_empty())
        .map(|s| s.to_string())
        .collect()
}

fn get_word_id(
    client: &mut Client,
    cache: &mut HashMap<String, i32>,
    word: &str,
    stmt_select: &Statement,
    stmt_insert: &Statement,
) -> Result<i32, postgres::Error> {
    if let Some(id) = cache.get(word) {
        return Ok(*id);
    }
    if let Some(row) = client.query_opt(stmt_select, &[&word])? {
        let id: i32 = row.get(0);
        cache.insert(word.to_string(), id);
        return Ok(id);
    }
    let row = client.query_one(stmt_insert, &[&word])?;
    let id: i32 = row.get(0);
    if id % 1000 == 0 {
        println!("Cached {} unique words (last ID: {})", cache.len(), id);
    }
    cache.insert(word.to_string(), id);
    Ok(id)
}

fn flush_batch(client: &mut Client, stmt: &Statement, batch: &[(i32, i32, i32)]) -> Result<(), postgres::Error> {
    if batch.is_empty() { return Ok(()); }
    let mut tx = client.transaction()?;
    for (p1, p2, next) in batch {
        tx.execute(stmt, &[p1, p2, next])?;
    }
    tx.commit()?;
    Ok(())
}

fn train_from_corpus(path: &str) -> Result<(), Box<dyn std::error::Error>> {
    let mut client = match connect_db() {
        Some(c) => c,
        None => return Ok(()),
    };

    client.execute(
        "INSERT INTO markov_words (id, word) VALUES ($1, $2) ON CONFLICT (id) DO NOTHING",
        &[&EMPTY_WORD_ID, &EMPTY_WORD],
    )?;

    let select_stmt = client.prepare("SELECT id FROM markov_words WHERE word = $1")?;
    let insert_stmt = client.prepare(
        "INSERT INTO markov_words (word) VALUES ($1) ON CONFLICT (word) DO UPDATE SET word=EXCLUDED.word RETURNING id",
    )?;
    let upsert_stmt = client.prepare(
        "INSERT INTO markov_sequences (p1, p2, next_id, freq) VALUES ($1,$2,$3,1) ON CONFLICT (p1, p2, next_id) DO UPDATE SET freq = markov_sequences.freq + 1",
    )?;

    let re_lt = Regex::new(r"(?<!\w)['\-](?!\w)")?;
    let re_other = Regex::new(r"[^\w\s'-]")?;

    let file = File::open(path)?;
    let reader = BufReader::new(file);
    let mut cache = HashMap::new();
    cache.insert(EMPTY_WORD.to_string(), EMPTY_WORD_ID);
    let mut batch: Vec<(i32, i32, i32)> = Vec::new();
    let mut processed = 0usize;
    let mut line_num = 0usize;

    for (idx, line) in reader.lines().enumerate() {
        line_num = idx;
        let line = line?;
        let words = tokenize_text(&line, &re_lt, &re_other);
        if words.is_empty() { continue; }
        let mut p1 = EMPTY_WORD_ID;
        let mut p2 = EMPTY_WORD_ID;
        for word in words {
            if word.len() > 100 {
                println!("Skipping excessively long token on line {}: '{}...'", idx+1, &word[..50.min(word.len())]);
                continue;
            }
            let next_id = get_word_id(&mut client, &mut cache, &word, &select_stmt, &insert_stmt)?;
            batch.push((p1, p2, next_id));
            processed += 1;
            p1 = p2;
            p2 = next_id;
            if batch.len() >= BATCH_SIZE {
                flush_batch(&mut client, &upsert_stmt, &batch)?;
                println!("Processed {} sequences (checkpoint)...", processed);
                batch.clear();
            }
        }
        batch.push((p1, p2, EMPTY_WORD_ID));
        processed += 1;
        if (idx + 1) % 10000 == 0 {
            flush_batch(&mut client, &upsert_stmt, &batch)?;
            println!("Committed up to line {}", idx + 1);
            batch.clear();
        }
    }

    flush_batch(&mut client, &upsert_stmt, &batch)?;
    println!(
        "Markov training complete. Processed {} sequences from {} lines.",
        processed,
        line_num + 1
    );
    println!("Final unique words count: {}", cache.len());
    Ok(())
}

fn main() {
    let args = Args::parse();
    if let Err(e) = train_from_corpus(&args.corpus_file) {
        eprintln!("Error: {}", e);
    }
}

