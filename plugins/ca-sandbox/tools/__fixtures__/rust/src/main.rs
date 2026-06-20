// Minimal ca-sandbox rust fixture entry point (AC-07).
//
// Std-only (no external crate to fetch) so the build is hermetic/offline. Prints a
// stable marker the multistack test matches to prove the built image runs.
fn main() {
    println!("RUST_FIXTURE OK=true");
}
