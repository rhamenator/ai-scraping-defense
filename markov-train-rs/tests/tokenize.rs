use markov_train_rs::tokenize_text;
use regex::Regex;

#[test]
fn tokenize_basic_sentence() {
    let re1 = Regex::new(r"[-']").unwrap();
    let re2 = Regex::new(r"[^\w\s'-]").unwrap();
    let re3 = Regex::new(r"^[-']+|[-']+$").unwrap();
    let tokens = tokenize_text("Hello, world! It's 2024.", &re1, &re2, &re3);
    assert_eq!(tokens, vec!["hello", "world", "its", "2024"]);
}

#[test]
fn tokenize_handles_empty() {
    let re1 = Regex::new(r"[-']").unwrap();
    let re2 = Regex::new(r"[^\w\s'-]").unwrap();
    let re3 = Regex::new(r"^[-']+|[-']+$").unwrap();
    let tokens = tokenize_text("?!", &re1, &re2, &re3);
    assert!(tokens.is_empty());
}
