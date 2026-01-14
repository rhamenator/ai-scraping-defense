fn main() {
    // Configure PyO3 for the current Python interpreter
    pyo3_build_config::use_pyo3_cfgs();
    // Add linker arguments needed for extension modules on some platforms
    pyo3_build_config::add_extension_module_link_args();
    // Ensure libpython is linked for unit tests and binary targets.
    let config = pyo3_build_config::get();
    if let Some(lib_dir) = &config.lib_dir {
        println!("cargo:rustc-link-search=native={lib_dir}");
    }
    if let Some(lib_name) = &config.lib_name {
        println!("cargo:rustc-link-lib={lib_name}");
    }
}
