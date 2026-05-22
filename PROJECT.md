# PROJECT — CloneScout

> A portable Python command-line tool that finds duplicate and near-duplicate directories across machines, archives, and file systems — without touching file contents.

## 1. Rationale

### The Problem

Over years of work, directories get copied between machines, zipped for backup, synced partially, renamed, and forgotten. The same project folder might exist as `C:\Backups\photos-2021\`, `/mnt/nas/old/photos/`, and buried inside `archive-jan.tar.gz` on yet another machine. The user knows duplication exists but has no safe, systematic way to find it.

### How People Solve It Today

- **Traditional dedup tools** (fdupes, jdupes, rdfind): Work on a single mounted filesystem, compare file contents byte-by-byte or via hashes. Require all data online and accessible simultaneously.
- **Cloud sync solutions** (rclone, Syncthing): Solve synchronization, not discovery of existing duplication.
- **Manual inspection**: Users browse around, guess, delete things, and sometimes regret it.

### Their Shortcomings

- Require all data to be mounted on one machine at the same time
- Cannot look inside archives without extracting them
- Operate at file level, not directory level — they'll tell you 10,000 files are duplicates but won't say "these two folders are essentially the same"
- Compute file hashes, which means reading every byte — slow and I/O-heavy on remote or cold storage
- Provide no tiered confidence levels — it's either "identical" or nothing

### The Promise

CloneScout works **where data are at rest**. Drop a single `.pyz` file onto any machine with Python 3.11+, scan locally, collect lightweight metadata, then analyze everything together offline. It finds duplicate and near-duplicate **directories** using only metadata (names, sizes, timestamps) — no file content reading. It gives you a prioritized, evidence-based report so you can make informed deduplication decisions.

## 2. Scope

### In Scope

- Recursive metadata scanning of local directories
- Scanning inside `.zip` and `.tar`/`.tar.gz`/`.tgz` files (without extraction)
- Configurable scan roots, exclusion rules, and parameters via TOML
- Portable output format (metadata archives as zip files)
- Merging scan results from multiple machines into a combined archive
- Detecting duplicate/near-duplicate directory pairs using LSH + MinHash on metadata features
- Tiered matching with configurable feature tiers
- Generating prioritized reports (largest duplicates first by default)
- Running on Windows, Linux, FreeBSD and what not with Python 3.11+ and no external dependencies
- Distribution as a single `.pyz` file via GitHub Releases

### Out of Scope

- Reading file contents or computing file hashes
- Performing any deletion, moving, or deduplication actions
- Real-time or continuous monitoring
- Network scanning or remote filesystem access (the tool runs locally; user transfers results)
- GUI or web interface
- Symlink/hardlink deduplication
- Database backend (all state lives in portable archive files)

## 3. User Experience

### Installation

There is no installation. However, there are preparation steps:

- Download the latest release from GitHub Releases: `clonescout-latest.pyz`
- Run `python3 clonescout-latest.pyz` without arguments. This displays help message and advises to run `python3 clonescout-latest.pyz sample config` which prints sample TOML config file to the stdout

### Configuration

- Save TOML config file to `clonescout.toml` and edit it: specify roots (scan starting points), output file name, exclusion rules, and other parameters


### Metadata Collection

- Run `python3 clonescout-latest.pyz scan` and get zip file with metadata of recursively scanned directories
- Repeat this step at every machine where data are at rest
- Gather metadata files in one place manually and run `python3 clonescout-latest.pyz merge` to get combined metadata archive

### Analysis

- Run `python3 clonescout-latest.pyz report`, it will build Markdown report on duplicate directories giving priority to the pairs that weight the most (this preference can be changed in the config)
- Use your subject knowledge and third-party tools to further investigate the duplication and take appropriate actions

## 4. Architecture Principles

### Metadata

File is uniquely identified by six components:

- **Node name**: user-assigned name of a machine, on which scanning is performed (defaults to socket.gethostname())
- **Anchor**: on file systems, "" on Posix systems or "C:" / "D:" etc. on Windows; for archives: Posix path to archive file
- **Folder parent**: Posix path to the file folder's parent directory, without leading or trailing slash
- **Folder name**: name of the file's folder
- **Stem**: file stem, as in Python's `pathlib`
- **Suffix**: file suffix, as in Python's `pathlib`

Gathered file features include:

- **ext**: extension, suffix without leading dot, capitalized (optionaly normalized, e.g. ".yml" → "YAML")
- **Size**: file size in bytes, integer
- **mtime**: file's mtime, without decimal part, integer

### Metadata Storage

Metadata are stored as nested dictionaries with node names on level 1 of the hierahchy, anchors on level 2, etc. with (ext, size, mtime) tuples as leaves of the tree. 
For compactness, each literal on the hierarchy is replaced with corresponding vocabulary index.

Vocabulary and metadata are serialized as a list and JSON, respectively, in a compressed pickle file.

On merge, common vocabulary is built first, then all metadata dictionaries are recoded and re-serialized.

### Analysis

Duplicate folder candidates are searched for using LSH + MinHash. 
Folder features of several tiers are used:

- T1 is "folder name + stem + ext + size", 
- T2 is "stem + ext + size + mtime", 
- T3 is "stem + ext + size"

Other tiers might be used. When a folder is identified as a duplicate candidate on one tier, it's excluded from further analysis.
