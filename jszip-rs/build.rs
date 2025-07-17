fn main() {
    // Configure PyO3 for the current Python interpreter
    pyo3_build_config::use_pyo3_cfgs();
    // Add linker arguments needed for extension modules on some platforms
    pyo3_build_config::add_extension_module_link_args();
    // Explicitly link to libpython for unit tests
    println!("cargo:rustc-link-lib=python3.12");
}
