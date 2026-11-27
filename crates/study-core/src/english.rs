// SPDX-License-Identifier: GPL-3.0-or-later
use crate::Result;

#[derive(Default)]
pub struct EnglishLexicon(Vec<(String, u16)>);

impl EnglishLexicon {
    pub fn from_index(index: &str) -> Result<Self> {
        let mut entries = Vec::new();
        let mut previous = "";
        for row in index.lines() {
            let (word, rank) = row.split_once('\t').ok_or("invalid-english-index")?;
            if word <= previous || !word.bytes().all(|c| c.is_ascii_lowercase() || c == b'\'') {
                return Err("invalid-english-index".into());
            }
            entries.push((word.to_string(), rank.parse().map_err(|_| "invalid-english-index")?));
            previous = word;
        }
        Ok(Self(entries))
    }

    pub(crate) fn contains(&self, lower: &str) -> bool {
        self.0.binary_search_by(|(word, _)| word.as_str().cmp(lower)).is_ok()
    }

    pub(crate) fn complete(&self, raw: &str, lower: &str) -> Vec<String> {
        let start = self.0.partition_point(|(word, _)| word.as_str() <= lower);
        let mut matches: Vec<_> = self.0[start..].iter().take_while(|(word, _)| word.starts_with(lower)).collect();
        matches.sort_unstable_by(|a, b| a.1.cmp(&b.1).then_with(|| a.0.cmp(&b.0)));
        let uppercase = raw.bytes().filter(u8::is_ascii_alphabetic).count() > 1
            && !raw.bytes().any(|c| c.is_ascii_lowercase());
        matches.into_iter().take(3).map(|(word, _)| {
            let suffix = &word[lower.len()..];
            if uppercase { raw.to_string() + &suffix.to_ascii_uppercase() } else { raw.to_string() + suffix }
        }).collect()
    }
}
