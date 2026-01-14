use jszip_rs::{
    create_fake_js_zip, generate_file_content, generate_realistic_filename, rand_string,
};
use std::path::PathBuf;

#[test]
fn random_string_length() {
    let s = rand_string(10);
    assert_eq!(s.len(), 10);
}

#[test]
fn content_at_least_size() {
    let data = generate_file_content("test", 64);
    assert!(data.len() >= 64);
}

#[test]
fn filename_has_js_extension() {
    let name = generate_realistic_filename().unwrap();
    assert!(name.ends_with(".js"));
}

#[test]
fn zip_file_created() {
    let dir = tempfile::tempdir().unwrap();
    let path = create_fake_js_zip(1, Some(dir.path().to_string_lossy().to_string()))
        .unwrap()
        .unwrap();
    assert!(PathBuf::from(&path).exists());
}
