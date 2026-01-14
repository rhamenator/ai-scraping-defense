// SIMD optimizations are enabled via .cargo/config.toml
// The compiler auto-vectorizes random number generation and string operations
// when compiled with target-cpu=native and SSE/AVX flags

use postgres::{Client, NoTls};
use pyo3::prelude::*;
use rand::distributions::WeightedIndex;
use rand::prelude::*;
use std::env;
use std::fs;

fn get_pg_password() -> Option<String> {
    let path = env::var("PG_PASSWORD_FILE").unwrap_or_else(|_| "/run/secrets/pg_password".into());
    fs::read_to_string(path).ok().map(|s| s.trim().to_string())
}

fn get_connection() -> Result<Client, postgres::Error> {
    let host = env::var("PG_HOST").unwrap_or_else(|_| "postgres".into());
    let port = env::var("PG_PORT").unwrap_or_else(|_| "5432".into());
    let db = env::var("PG_DBNAME").unwrap_or_else(|_| "markovdb".into());
    let user = env::var("PG_USER").unwrap_or_else(|_| "markovuser".into());
    let password = get_pg_password().unwrap_or_default();
    let conn_str = format!(
        "host={} port={} dbname={} user={} password={}",
        host, port, db, user, password
    );
    Client::connect(&conn_str, NoTls)
}

fn get_word_id(client: &mut Client, word: &str) -> i32 {
    if word.is_empty() {
        return 1;
    }
    if let Ok(row) = client.query_opt("SELECT id FROM markov_words WHERE word = $1", &[&word]) {
        row.map(|r| r.get::<usize, i32>(0)).unwrap_or(1)
    } else {
        1
    }
}

fn get_next_word_from_db(client: &mut Client, w1: i32, w2: i32) -> Option<String> {
    let stmt = "SELECT w.word, s.freq FROM markov_sequences s JOIN markov_words w ON s.next_id = w.id WHERE s.p1 = $1 AND s.p2 = $2 ORDER BY s.freq DESC, random() LIMIT 20";
    match client.query(stmt, &[&w1, &w2]) {
        Ok(rows) if !rows.is_empty() => {
            let words: Vec<String> = rows.iter().map(|r| r.get(0)).collect();
            let freqs: Vec<i32> = rows.iter().map(|r| r.get(1)).collect();
            let total: i32 = freqs.iter().sum();
            let mut rng = thread_rng();
            let idx = if total > 0 {
                let dist = WeightedIndex::new(freqs.iter().map(|f| *f as f64)).unwrap();
                dist.sample(&mut rng)
            } else {
                rng.gen_range(0..words.len())
            };
            Some(words[idx].clone())
        }
        _ => None,
    }
}

fn generate_markov_text_from_db(sentences: usize) -> String {
    let mut client = match get_connection() {
        Ok(c) => c,
        Err(_) => return "<p>Content generation unavailable.</p>".to_string(),
    };
    let mut result = String::new();
    let mut w1 = 1;
    let mut w2 = 1;
    let mut word_count = 0usize;
    let mut current_para: Vec<String> = Vec::new();
    let mut rng = thread_rng();
    let max_words = sentences * rng.gen_range(15..=30);
    while word_count < max_words {
        match get_next_word_from_db(&mut client, w1, w2) {
            Some(ref word) if !word.is_empty() => {
                current_para.push(html_escape::encode_text(word).to_string());
                word_count += 1;
                w1 = w2;
                w2 = get_word_id(&mut client, word);
                if [".", "!", "?"].iter().any(|p| word.ends_with(p)) && current_para.len() > 5 {
                    result.push_str("<p>");
                    result.push_str(&current_para.join(" "));
                    result.push_str("</p>\n");
                    current_para.clear();
                    w1 = 1;
                    w2 = 1;
                }
            }
            _ => {
                if !current_para.is_empty() {
                    result.push_str("<p>");
                    result.push_str(&current_para.join(" "));
                    result.push_str(".</p>\n");
                    current_para.clear();
                }
                w1 = 1;
                w2 = 1;
                if word_count >= max_words / 2 {
                    break;
                }
            }
        }
    }
    if !current_para.is_empty() {
        result.push_str("<p>");
        result.push_str(&current_para.join(" "));
        result.push_str(".</p>\n");
    }
    if result.is_empty() {
        "<p>Could not generate content.</p>".into()
    } else {
        result
    }
}

fn rand_string(len: usize) -> String {
    use rand::distributions::Alphanumeric;
    thread_rng()
        .sample_iter(&Alphanumeric)
        .take(len)
        .map(char::from)
        .collect()
}

/// Generate fake links with pre-allocated capacity for better performance.
/// SIMD optimizations apply to string concatenation and array operations.
fn generate_fake_links(count: usize, depth: usize) -> Vec<String> {
    let mut rng = thread_rng();
    let mut links = Vec::with_capacity(count);
    for _ in 0..count {
        let link_type = ["page", "js", "data", "css"][rng.gen_range(0..4)];
        let num_dirs = rng.gen_range(0..=depth);
        let dirs: Vec<String> = (0..num_dirs)
            .map(|_| rand_string(rng.gen_range(5..=8)))
            .collect();
        let filename_base = rand_string(10);
        let (ext, prefix) = match link_type {
            "page" => (".html", "/page/"),
            "js" => (".js", "/js/"),
            "data" => (if rng.gen_bool(0.5) { ".json" } else { ".xml" }, "/data/"),
            _ => (".css", "/styles/"),
        };
        let mut full = String::from("/tarpit");
        full.push_str(prefix);
        if !dirs.is_empty() {
            full.push_str(&dirs.join("/"));
            full.push('/');
        }
        full.push_str(&filename_base);
        full.push_str(ext);
        links.push(full.replace("//", "/"));
    }
    links
}

fn generate_page() -> String {
    let content = generate_markov_text_from_db(15);
    let links = generate_fake_links(7, 3);
    let mut link_html = String::from("<ul>\n");
    for link in &links {
        let text_base = link
            .split('/')
            .next_back()
            .unwrap_or("link")
            .split('.')
            .next()
            .unwrap_or("link");
        let mut text = text_base
            .chars()
            .map(|c| if c == '_' || c == '-' { ' ' } else { c })
            .collect::<String>();
        if text.is_empty() {
            text = "Resource Link".into();
        }
        let safe = html_escape::encode_text(&text);
        link_html.push_str(&format!("    <li><a href=\"{}\">{}</a></li>\n", link, safe));
    }
    link_html.push_str("</ul>\n");
    let title = rand_string(8);
    format!("<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\"><title>{} - System Documentation</title><meta name=\"robots\" content=\"noindex, nofollow\"></head><body><h1>{}</h1>{}<h2>Further Reading:</h2>{}<a href=\"/internal-docs/admin\" class=\"footer-link\">Admin Console</a></body></html>",
        title, title, content, link_html)
}

#[pyfunction]
fn generate_dynamic_tarpit_page() -> PyResult<String> {
    Ok(generate_page())
}

#[pymodule]
fn tarpit_rs(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(generate_dynamic_tarpit_page, m)?)?;
    Ok(())
}
