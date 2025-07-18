use pyo3::prelude::*;
use rand::{distributions::Alphanumeric, Rng};
use zip::write::FileOptions;
use chrono::Utc;
use std::fs::{self, File};
use std::io::Write;
use std::path::{Path, PathBuf};

const DEFAULT_ARCHIVE_DIR: &str = "/app/fake_archives";
const FILENAME_PREFIXES: [&str; 12] = [
    "analytics_bundle", "vendor_lib", "core_framework", "ui_component_pack",
    "polyfills_es6", "runtime_utils", "shared_modules", "feature_flags_data",
    "config_loader", "auth_client_sdk", "graph_rendering_engine", "data_sync_worker",
];
const FILENAME_SUFFIXES: [&str; 6] = ["_min", "_pack", "_bundle", "_lib", "_core", ""];
const FILENAME_EXT: &str = ".js";

fn rand_string(len: usize) -> String {
    rand::thread_rng()
        .sample_iter(&Alphanumeric)
        .take(len)
        .map(char::from)
        .collect()
}

#[pyfunction]
fn generate_realistic_filename() -> PyResult<String> {
    let mut rng = rand::thread_rng();
    let prefix = FILENAME_PREFIXES[rng.gen_range(0..FILENAME_PREFIXES.len())];
    let suffix = FILENAME_SUFFIXES[rng.gen_range(0..FILENAME_SUFFIXES.len())];
    let random_hash: String = rand_string(8).to_lowercase();
    Ok(format!("{}{}{}.{}", prefix, suffix, random_hash, "js"))
}

fn generate_file_content(name: &str, target_size: usize) -> Vec<u8> {
    let mut rng = rand::thread_rng();
    let mut content = format!("// Fake module: {}\n(function() {{\n", name);
    let vars = rng.gen_range(5..20);
    for _ in 0..vars {
        let var_name = rand_string(rng.gen_range(4..10));
        content.push_str(&format!("  var {} = {}\n",
            var_name,
            rng.gen_range(0..1000)));
    }
    content.push_str("})();\n");
    let mut bytes = content.into_bytes();
    if bytes.len() < target_size {
        let padding: String = rand_string(target_size - bytes.len());
        bytes.extend_from_slice(padding.as_bytes());
    }
    bytes
}

#[pyfunction(signature = (num_files, output_dir = None))]
fn create_fake_js_zip(num_files: usize, output_dir: Option<String>) -> PyResult<Option<String>> {
    let out_dir = output_dir.unwrap_or_else(|| DEFAULT_ARCHIVE_DIR.to_string());
    fs::create_dir_all(&out_dir).map_err(|e| PyErr::new::<pyo3::exceptions::PyIOError, _>(format!("Failed to create dir: {}", e)))?;
    let timestamp = Utc::now().format("%Y%m%d_%H%M%S");
    let archive_path = Path::new(&out_dir).join(format!("assets_{}.zip", timestamp));
    let file = File::create(&archive_path).map_err(|e| PyErr::new::<pyo3::exceptions::PyIOError, _>(format!("Failed to create zip: {}", e)))?;
    let mut zip = zip::ZipWriter::new(file);
    let options = FileOptions::default().compression_method(zip::CompressionMethod::Deflated);
    for _ in 0..num_files {
        let name = generate_realistic_filename()?;
        let size = rand::thread_rng().gen_range(5 * 1024..50 * 1024);
        let content = generate_file_content(&name, size);
        zip.start_file(name, options).map_err(|e| PyErr::new::<pyo3::exceptions::PyIOError, _>(format!("Zip error: {}", e)))?;
        zip.write_all(&content).map_err(|e| PyErr::new::<pyo3::exceptions::PyIOError, _>(format!("Write error: {}", e)))?;
    }
    zip.finish().map_err(|e| PyErr::new::<pyo3::exceptions::PyIOError, _>(format!("Finish zip error: {}", e)))?;
    Ok(Some(archive_path.to_string_lossy().to_string()))
}

#[pymodule]
fn jszip_rs(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(generate_realistic_filename, m)?)?;
    m.add_function(wrap_pyfunction!(create_fake_js_zip, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn filename_varies() {
        let f1 = generate_realistic_filename().unwrap();
        let f2 = generate_realistic_filename().unwrap();
        assert_ne!(f1, f2);
        assert!(f1.ends_with(".js"));
    }

    #[test]
    fn zip_created() {
        let dir = tempfile::tempdir().unwrap();
        let path = create_fake_js_zip(3, Some(dir.path().to_string_lossy().to_string())).unwrap().unwrap();
        assert!(PathBuf::from(&path).exists());
        fs::remove_file(path).unwrap();
    }
}
