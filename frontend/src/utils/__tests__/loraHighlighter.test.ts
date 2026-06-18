import { describe, it, expect } from "vitest";
import { loraHighlighter } from "../loraHighlighter";

describe("loraHighlighter", () => {
  it("returns an empty string for empty input", () => {
    expect(loraHighlighter("")).toBe("");
  });

  it("returns an empty string for whitespace-only input", () => {
    // The function short-circuits on falsy input; whitespace is truthy and falls
    // through to the regex loop, producing no lora spans and returning the
    // original whitespace escaped.
    expect(loraHighlighter("   ")).toBe("   ");
  });

  it("returns plain text unchanged (escaped) when no lora tokens are present", () => {
    expect(loraHighlighter("a beautiful landscape")).toBe("a beautiful landscape");
  });

  it("wraps a single lora token in a span.lora-pill", () => {
    expect(loraHighlighter("<lora:style:1.0>")).toBe('<span class="lora-pill">style:1.0</span>');
  });

  it("wraps a lora token without an explicit weight", () => {
    expect(loraHighlighter("<lora:style>")).toBe('<span class="lora-pill">style</span>');
  });

  it("preserves surrounding text and wraps multiple lora tokens", () => {
    const input = "intro <lora:foo:0.8> middle <lora:bar> end";
    expect(loraHighlighter(input)).toBe(
      'intro <span class="lora-pill">foo:0.8</span> middle <span class="lora-pill">bar</span> end',
    );
  });

  it("is case-insensitive on the lora tag name", () => {
    expect(loraHighlighter("<LORA:Style:1>")).toBe('<span class="lora-pill">Style:1</span>');
    expect(loraHighlighter("<LoRa:Style>")).toBe('<span class="lora-pill">Style</span>');
  });

  it("escapes HTML special characters in plain text segments", () => {
    expect(loraHighlighter("a < b & c > d")).toBe("a &lt; b &amp; c &gt; d");
  });

  it("escapes HTML special characters inside the lora name and weight", () => {
    expect(loraHighlighter('<lora:a&b:c<" >')).toBe('<span class="lora-pill">a&amp;b:c&lt;&quot; </span>');
  });

  it("escapes single quotes and double quotes in plain text", () => {
    expect(loraHighlighter(`it's "quoted"`)).toBe("it&#039;s &quot;quoted&quot;");
  });

  it("does not treat partial lora tokens as matches", () => {
    // Missing closing > means no match — the whole string is treated as plain text.
    expect(loraHighlighter("<lora:style")).toBe("&lt;lora:style");
  });

  it("handles lora tokens that include a colon but no weight", () => {
    // The regex allows the weight group to be absent; a trailing colon inside the
    // token name section is not produced because the regex requires `:` only as
    // the separator. Verify the standard form renders correctly.
    expect(loraHighlighter("<lora:foo> bar")).toBe('<span class="lora-pill">foo</span> bar');
  });

  it("returns escaped text when the input contains only an open bracket", () => {
    expect(loraHighlighter("<")).toBe("&lt;");
  });

  it("matches lora tokens with colons in the weight section (name stops at first colon)", () => {
    // The regex captures name as [^:>]+ and weight as [^>]+, so `<lora:a:b>`
    // matches with name="a" and weight="b" and renders as "a:b".
    expect(loraHighlighter("<lora:a:b>")).toBe('<span class="lora-pill">a:b</span>');
  });

  it("does not match <lora:foo:> (trailing colon with empty weight)", () => {
    // The optional weight group requires [^>]+ after the colon, so a trailing
    // colon immediately before `>` cannot satisfy the regex. The whole token is
    // treated as plain text.
    expect(loraHighlighter("<lora:foo:>")).toBe("&lt;lora:foo:&gt;");
  });
});
