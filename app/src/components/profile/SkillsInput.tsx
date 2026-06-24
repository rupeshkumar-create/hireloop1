"use client";

import { useEffect, useRef, useState } from "react";
import { fetchSkillSuggestions } from "@/lib/api/skills";

/**
 * Comma-separated skills input with autocomplete from the backend's canonical
 * skills vocabulary. Drop-in for a plain text Input: same {value, onChange}
 * (the value stays a comma-separated string), with a suggestions dropdown for
 * the token currently being typed (text after the last comma).
 */
export function SkillsInput({
  label,
  value,
  onChange,
  className = "",
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  className?: string;
  placeholder?: string;
}) {
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);

  // The fragment after the last comma is what the user is currently typing.
  const currentToken = value.split(",").pop()?.trim() ?? "";

  useEffect(() => {
    let cancelled = false;
    if (currentToken.length < 2) {
      setSuggestions([]);
      return;
    }
    const id = window.setTimeout(async () => {
      const out = await fetchSkillSuggestions(currentToken, 8);
      if (cancelled) return;
      // Hide skills already present in the list.
      const have = new Set(
        value
          .split(",")
          .map((s) => s.trim().toLowerCase())
          .filter(Boolean)
      );
      setSuggestions(out.filter((s) => !have.has(s.toLowerCase())));
      setActive(0);
    }, 180);
    return () => {
      cancelled = true;
      window.clearTimeout(id);
    };
  }, [currentToken, value]);

  // Close the dropdown on outside click.
  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  function applySuggestion(skill: string) {
    const parts = value.split(",");
    parts[parts.length - 1] = ` ${skill}`;
    // Leave a trailing ", " so the next skill can be typed immediately.
    onChange(parts.join(",").replace(/^\s+/, "") + ", ");
    setSuggestions([]);
    setOpen(false);
  }

  const showList = open && suggestions.length > 0;

  return (
    <div className={`relative block ${className}`} ref={boxRef}>
      <span className="mb-1 block text-sm font-medium text-ink-700">{label}</span>
      <input
        type="text"
        value={value}
        placeholder={placeholder}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (!showList) return;
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((a) => Math.min(a + 1, suggestions.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === "Enter" && suggestions[active]) {
            e.preventDefault();
            applySuggestion(suggestions[active]);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
        className="w-full rounded-lg border border-ink-100 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-accent-ring"
        autoComplete="off"
      />
      {showList && (
        <ul className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-lg border border-ink-100 bg-white py-1 shadow-lg">
          {suggestions.map((s, i) => (
            <li key={s}>
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault();
                  applySuggestion(s);
                }}
                onMouseEnter={() => setActive(i)}
                className={`block w-full px-3 py-2 text-left text-sm ${
                  i === active ? "bg-ink-50 text-accent" : "text-ink-700"
                }`}
              >
                {s}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
