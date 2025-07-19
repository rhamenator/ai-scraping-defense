use pyo3::prelude::*;
use postgres::{Client, NoTls};
use regex::Regex;
use std::collections::HashMap;
use std::env;
use std::fs::File;
use std::io::{BufRead, BufReader};

const EMPTY_WORD: &str = "";
const EMPTY_WORD_ID: i32 = 1;
const BATCH_SIZE: usize = 10000;

fn get_pg_password() -> Option<String> {
    let path = env::var("PG_PASSWORD_FILE").unwrap_or_else(|_| "/run/secrets/pg_password".into());
    std::fs::read_to_string(path).ok().map(|s| s.trim().to_string())
}

fn connect_db() -> Result<Client, postgres::Error> {
    let host = env::var("PG_HOST").unwrap_or_else(|_| "localhost".into());
    let port = env::var("PG_PORT").unwrap_or_else(|_| "5432".into());
    let db = env::var("PG_DBNAME").unwrap_or_else(|_| "markovdb".into());
    let user = env::var("PG_USER").unwrap_or_else(|_| "markovuser".into());
    let password = get_pg_password().unwrap_or_default();
    let conn_str = format!("host={} port={} dbname={} user={} password={}", host, port, db, user, password);
    Client::connect(&conn_str, NoTls)
}

fn tokenize_text(text: &str, re1: &Regex, re2: &Regex, re3: &Regex) -> Vec<String> {
    let mut s = re1.replace_all(text, "").to_lowercase();
    s = re2.replace_all(&s, "").to_string();
    s.split_whitespace()
        .map(|w| re3.replace_all(w, "").to_string())
        .filter(|w| !w.is_empty())
        .collect()
}

fn get_word_id(client: &mut Client, cache: &mut HashMap<String, i32>, word: &str) -> Result<i32, postgres::Error> {
    if let Some(&id) = cache.get(word) {
        return Ok(id);
    }
    if word.is_empty() {
        cache.insert(String::new(), EMPTY_WORD_ID);
        return Ok(EMPTY_WORD_ID);
    }
    if let Some(row) = client.query_opt("SELECT id FROM markov_words WHERE word = $1", &[&word])? {
        let id: i32 = row.get(0);
        cache.insert(word.to_string(), id);
        return Ok(id);
    }
    let row = client.query_one(
        "INSERT INTO markov_words (word) VALUES ($1) ON CONFLICT (word) DO UPDATE SET word=EXCLUDED.word RETURNING id",
        &[&word],
    )?;
    let id: i32 = row.get(0);
    cache.insert(word.to_string(), id);
    Ok(id)
}

#[pyfunction]
fn train_from_corpus_rs(corpus_path: String) -> PyResult<()> {
    let mut client = connect_db().map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("DB connect error: {}", e)))?;

    let file = File::open(&corpus_path).map_err(|e| pyo3::exceptions::PyIOError::new_err(format!("{}", e)))?;
    let reader = BufReader::new(file);

    let re1 = Regex::new(r"(?<!\w)['\-](?!\w)").unwrap();
    let re2 = Regex::new(r"[^\w\s'-]").unwrap();
    let re3 = Regex::new(r"^[-']+|[-']+$").unwrap();

    client.execute(
        "INSERT INTO markov_words (id, word) VALUES ($1, $2) ON CONFLICT (id) DO NOTHING",
        &[&EMPTY_WORD_ID, &EMPTY_WORD],
    ).ok();

    let mut cache: HashMap<String, i32> = HashMap::new();
    cache.insert(String::new(), EMPTY_WORD_ID);

    let mut batch: Vec<(i32, i32, i32)> = Vec::new();
    let stmt = client.prepare("INSERT INTO markov_sequences (p1, p2, next_id, freq) VALUES ($1, $2, $3, 1) ON CONFLICT (p1, p2, next_id) DO UPDATE SET freq = markov_sequences.freq + 1;").unwrap();

    for line in reader.lines() {
        let line = line.map_err(|e| pyo3::exceptions::PyIOError::new_err(format!("{}", e)))?;
        let words = tokenize_text(&line, &re1, &re2, &re3);
        if words.is_empty() { continue; }
        let mut p1 = EMPTY_WORD_ID;
        let mut p2 = EMPTY_WORD_ID;
        for word in words {
            if word.len() > 100 { continue; }
            let next_id = get_word_id(&mut client, &mut cache, &word)
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("DB error: {}", e)))?;
            batch.push((p1, p2, next_id));
            if batch.len() >= BATCH_SIZE {
                for (a,b,c) in &batch { client.execute(&stmt, &[a,b,c]).ok(); }
                batch.clear();
            }
            p1 = p2;
            p2 = next_id;
        }
        batch.push((p1, p2, EMPTY_WORD_ID));
        if batch.len() >= BATCH_SIZE {
            for (a,b,c) in &batch { client.execute(&stmt, &[a,b,c]).ok(); }
            batch.clear();
        }
    }
    if !batch.is_empty() {
        for (a,b,c) in &batch { client.execute(&stmt, &[a,b,c]).ok(); }
    }
    Ok(())
}

#[pymodule]
fn markov_train_rs(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(train_from_corpus_rs, m)?)?;
    Ok(())
}
