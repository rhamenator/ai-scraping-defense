use pyo3::prelude::*;
use redis::{FromRedisValue, Value};
use std::env;
use std::fs;

fn get_password() -> Option<String> {
    if let Ok(path) = env::var("REDIS_PASSWORD_FILE") {
        fs::read_to_string(path).ok().map(|s| s.trim().to_string())
    } else {
        None
    }
}

fn get_connection(db: u32) -> redis::RedisResult<redis::Connection> {
    let host = env::var("REDIS_HOST").unwrap_or_else(|_| "localhost".into());
    let password = get_password();
    let url = if let Some(pw) = password {
        format!("redis://:{}@{}:{}/{}", pw, host, 6379, db)
    } else {
        format!("redis://{}:{}/{}", host, 6379, db)
    };
    let client = redis::Client::open(url)?;
    client.get_connection()
}

fn query_frequency(ip: &str, db: u32, window_seconds: u64, prefix: &str, ttl: u64) -> redis::RedisResult<(i64, f64)> {
    let mut con = get_connection(db)?;
    let now = chrono::Utc::now().timestamp_micros() as f64 / 1_000_000.0;
    let window_start = now - window_seconds as f64;
    let key = format!("{}{}", prefix, ip);
    let now_str = format!("{:.6}", now);

    let mut pipe = redis::pipe();
    pipe.cmd("ZREMRANGEBYSCORE")
        .arg(&key)
        .arg("-inf")
        .arg(format!("({}", window_start))
        .cmd("ZADD")
        .arg(&key)
        .arg(now)
        .arg(&now_str)
        .cmd("ZCOUNT")
        .arg(&key)
        .arg(window_start)
        .arg(now)
        .cmd("ZRANGE")
        .arg(&key)
        .arg(-2)
        .arg(-1)
        .arg("WITHSCORES")
        .cmd("EXPIRE")
        .arg(&key)
        .arg(ttl);
    let results: Vec<Value> = pipe.query(&mut con)?;

    let count: i64 = if results.len() > 2 { FromRedisValue::from_redis_value(&results[2]).unwrap_or(0) } else { 0 };
    let entries: Vec<(String, f64)> = if results.len() > 3 { FromRedisValue::from_redis_value(&results[3]).unwrap_or_default() } else { vec![] };

    let mut time_since = -1.0f64;
    if entries.len() > 1 {
        let last_score = entries[entries.len() - 2].1;
        let diff = now - last_score;
        time_since = (diff * 1000.0).round() / 1000.0;
    } else if entries.len() == 1 && count == 1 {
        time_since = -1.0;
    }

    Ok((std::cmp::max(0, count - 1), time_since))
}

#[pyfunction]
fn get_realtime_frequency_features(ip: String, db: u32, window_seconds: u64, prefix: String, ttl: u64) -> PyResult<(i64, f64)> {
    match query_frequency(&ip, db, window_seconds, &prefix, ttl) {
        Ok(res) => Ok(res),
        Err(e) => Err(pyo3::exceptions::PyRuntimeError::new_err(format!("Redis error: {}", e))),
    }
}

#[pymodule]
fn frequency_rs(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(get_realtime_frequency_features, m)?)?;
    Ok(())
}


