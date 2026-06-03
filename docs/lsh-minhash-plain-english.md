# A Plain-English Tour of LSH + MinHash in CloneScout

## What CloneScout is trying to do

CloneScout visits a pile of folders. In each folder it collects metadata — folder name, file name, extension, size, last-modified time.

The job: find folders that are "mostly the same content" — duplicates, backups, near-copies.

A folder is described by a **set of file fingerprints**: one small tuple per file, made up of pieces like `(name, extension, size)`. Two folders are "the same" if their fingerprints overlap a lot.

---

## Why the obvious approach is too slow

The obvious thing: pick any two folders, count how many file fingerprints they share, divide by the total. If the ratio is high, they're duplicates. This ratio is known as the Jaccard similarity.

The problem is **scale**. With thousands of folders, the number of pairs to check is in the millions. CloneScout gets around this with two stacked tricks:

1. **MinHash** — turn every folder into a short signature. Comparing signatures is much cheaper than comparing full folder contents.
2. **Locality-Sensitive Hashing (LSH)** — instead of comparing every signature to every other one, only compare pairs that are *likely* to match.

---

## MinHash — turning a folder into a signature

Give every file a "score" — a stable, unpredictable number derived from its metadata. The same file gets the same score.

Now, for each scoring rule (we'll call each one a "slot"), take the smallest score among all files in a folder. Do this across many slots — each with its own scoring rule — and you get a short list of minimums. That list is the MinHash signature of the folder.

The clever bit: if two folders share a file, that file might be the one that scored lowest in a given slot — and then both folders will have the same minimum for that slot. The more files they share, the more slots will match. So instead of comparing full folder contents, CloneScout just compares these short lists of minimums — and that's fast.

---

## LSH — finding candidates without comparing everyone

Even with short signatures, comparing every folder to every other folder is expensive. LSH fixes this.

Split the signature into chunks called **bands**. Two folders become candidates if *at least one band* matches exactly.

- If folders are very similar, many slots match — the chance that at least one whole band lines up is high.
- If folders are very different, it's unlikely any full band will match.

So similar folders tend to land in the same bucket; different ones mostly don't. CloneScout then only checks pairs that share a bucket.

---

## The tier system — T1, T2, T3

CloneScout runs the engine three times with different file attributes and thresholds:

| Tier | What's compared per file                    | Threshold | Feel                                |
|------|---------------------------------------------|-----------|-------------------------------------|
| T1   | folder name, file name, extension, size     | 0.80      | "Almost certainly the same"         |
| T2   | file name, extension, size, modified time   | 0.70      | "Looks like a renamed copy"  |
| T3   | file name, extension, size                  | 0.60      | "Rough match, different era"        |

When a pair is matched in an earlier tier, **both folders are removed from the pool** for later tiers — the user sees the strongest match, not every possible one.

The final list of folder pairs is grouped by Tier, and within each tier sorted by the total size of shared files, largest first.

---

## A one-paragraph mental model

> For every folder, build a short signature by taking the smallest per-slot score across its files. Split the signature into chunks. Folders with matching chunks become candidates. Verify candidates exactly. Do this three times with progressively looser rules.
