# Rust Release Profile Optimization

This project ships multiple Rust crates that are compiled into shared libraries.
To keep runtime performance consistent, each crate uses the same release
profile settings.

## Release Profile

```toml
[profile.release]
opt-level = 3
lto = "thin"
codegen-units = 1
strip = true
panic = "abort"
```

## Why These Settings?

- `opt-level = 3` enables the most aggressive optimizations.
- `lto = "thin"` improves cross-crate optimization without the full LTO cost.
- `codegen-units = 1` helps the compiler optimize across the entire crate.
- `strip = true` reduces release binary size.
- `panic = "abort"` removes unwind overhead in release builds.

## How to Build

```bash
cargo build --release
```
