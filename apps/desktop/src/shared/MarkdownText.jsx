import React from "react";

export function MarkdownText({ value, fallback = "", className = "" }) {
  const text = stringifyMarkdownValue(value, fallback);
  const blocks = parseMarkdownBlocks(text);
  if (!blocks.length) return null;
  return (
    <div className={`markdown-text ${className}`.trim()}>
      {blocks.map((block, index) => renderBlock(block, index))}
    </div>
  );
}

export function MarkdownInline({ value, fallback = "" }) {
  return <>{parseInline(stringifyMarkdownValue(value, fallback), "inline")}</>;
}

function stringifyMarkdownValue(value, fallback = "") {
  if (value == null || value === "") return fallback;
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function parseMarkdownBlocks(value) {
  const text = String(value || "").replace(/\r\n?/g, "\n").trim();
  if (!text) return [];
  const lines = text.split("\n");
  const blocks = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    const fence = line.match(/^\s*```([^`]*)\s*$/);
    if (fence) {
      const codeLines = [];
      index += 1;
      while (index < lines.length && !/^\s*```\s*$/.test(lines[index])) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push({ type: "code", language: fence[1].trim(), text: codeLines.join("\n") });
      continue;
    }

    const heading = line.match(/^\s{0,3}(#{1,6})\s+(.+)$/);
    if (heading) {
      blocks.push({ type: "heading", level: Math.min(heading[1].length, 3), text: heading[2].trim() });
      index += 1;
      continue;
    }

    if (isTableStart(lines, index)) {
      const table = parseMarkdownTable(lines, index);
      blocks.push(table.block);
      index = table.nextIndex;
      continue;
    }

    if (isHorizontalRule(line)) {
      blocks.push({ type: "hr" });
      index += 1;
      continue;
    }

    if (isUnorderedListLine(line)) {
      const parsed = parseListBlock(lines, index, false);
      blocks.push(parsed.block);
      index = parsed.nextIndex;
      continue;
    }

    if (isOrderedListLine(line)) {
      const parsed = parseListBlock(lines, index, true);
      blocks.push(parsed.block);
      index = parsed.nextIndex;
      continue;
    }

    if (/^\s{0,3}>\s?/.test(line)) {
      const quoteLines = [];
      while (index < lines.length && /^\s{0,3}>\s?/.test(lines[index])) {
        quoteLines.push(lines[index].replace(/^\s{0,3}>\s?/, ""));
        index += 1;
      }
      blocks.push({ type: "quote", text: quoteLines.join("\n").trim() });
      continue;
    }

    const paragraph = [line.trim()];
    index += 1;
    while (
      index < lines.length &&
      lines[index].trim() &&
      !/^\s*```/.test(lines[index]) &&
      !/^\s{0,3}#{1,6}\s+/.test(lines[index]) &&
      !isTableStart(lines, index) &&
      !isHorizontalRule(lines[index]) &&
      !isUnorderedListLine(lines[index]) &&
      !isOrderedListLine(lines[index]) &&
      !/^\s{0,3}>\s?/.test(lines[index])
    ) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push({ type: "paragraph", text: paragraph.join("\n") });
  }
  return blocks;
}

function renderBlock(block, index) {
  if (block.type === "code") {
    return (
      <pre key={index}>
        <code>{block.text}</code>
      </pre>
    );
  }
  if (block.type === "heading") {
    const Tag = block.level === 1 ? "h3" : block.level === 2 ? "h4" : "h5";
    return <Tag key={index}>{parseInline(block.text, index)}</Tag>;
  }
  if (block.type === "ul") {
    return (
      <ul key={index}>
        {block.items.map((item, itemIndex) => renderListItem(item, `${index}-${itemIndex}`))}
      </ul>
    );
  }
  if (block.type === "ol") {
    return (
      <ol key={index}>
        {block.items.map((item, itemIndex) => renderListItem(item, `${index}-${itemIndex}`))}
      </ol>
    );
  }
  if (block.type === "quote") {
    return <blockquote key={index}>{parseInline(block.text, index)}</blockquote>;
  }
  if (block.type === "hr") {
    return <hr key={index} />;
  }
  if (block.type === "table") {
    return (
      <div className="markdown-table-wrap" key={index}>
        <table>
          <thead>
            <tr>
              {block.headers.map((cell, cellIndex) => (
                <th align={block.align[cellIndex] || undefined} key={cellIndex}>
                  {parseInline(cell, `${index}-h-${cellIndex}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {block.headers.map((_, cellIndex) => (
                  <td align={block.align[cellIndex] || undefined} key={cellIndex}>
                    {parseInline(row[cellIndex] || "", `${index}-${rowIndex}-${cellIndex}`)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return <p key={index}>{parseInline(block.text, index)}</p>;
}

function renderListItem(item, key) {
  const children = [];
  const content = item.task ? (
    <label className="markdown-task">
      <input type="checkbox" checked={item.checked} readOnly />
      <span>{parseInline(item.text, `${key}-task`)}</span>
    </label>
  ) : (
    parseInline(item.text, `${key}-text`)
  );
  children.push(<React.Fragment key={`${key}-content`}>{content}</React.Fragment>);
  if (item.children?.length) {
    const ChildTag = item.childrenOrdered ? "ol" : "ul";
    children.push(
      <ChildTag key={`${key}-children`}>
        {item.children.map((child, childIndex) => renderListItem(child, `${key}-${childIndex}`))}
      </ChildTag>
    );
  }
  return <li key={key}>{children}</li>;
}

function parseListBlock(lines, startIndex, ordered) {
  const items = [];
  let index = startIndex;
  while (index < lines.length) {
    const parsed = parseListLine(lines[index], ordered);
    if (!parsed || parsed.indent > 0) break;
    const item = listItemFromText(parsed.text);
    index += 1;

    const childLines = [];
    while (index < lines.length) {
      const child = parseListLine(lines[index], false) || parseListLine(lines[index], true);
      if (!child || child.indent === 0) break;
      childLines.push(stripListIndent(lines[index], child.indent));
      index += 1;
    }
    if (childLines.length) {
      const childBlock = parseListBlock(childLines, 0, isOrderedListLine(childLines[0]));
      item.children = childBlock.block.items;
      item.childrenOrdered = childBlock.block.type === "ol";
    }
    items.push(item);
  }
  return { block: { type: ordered ? "ol" : "ul", items }, nextIndex: index };
}

function parseListLine(line, ordered) {
  const pattern = ordered
    ? /^(\s*)\d+[.)]\s+(.+)$/
    : /^(\s*)[-*+]\s+(.+)$/;
  const match = String(line || "").match(pattern);
  if (!match) return null;
  return { indent: match[1].replace(/\t/g, "    ").length, text: match[2].trim() };
}

function listItemFromText(text) {
  const task = String(text || "").match(/^\[( |x|X)\]\s+(.*)$/);
  if (!task) return { text };
  return {
    text: task[2].trim(),
    task: true,
    checked: task[1].toLowerCase() === "x",
  };
}

function stripListIndent(line, indent) {
  return String(line || "").slice(Math.min(Number(indent || 0), String(line || "").length));
}

function isUnorderedListLine(line) {
  return /^\s*[-*+]\s+/.test(String(line || "")) && !isHorizontalRule(line);
}

function isOrderedListLine(line) {
  return /^\s*\d+[.)]\s+/.test(String(line || ""));
}

function isHorizontalRule(line) {
  return /^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/.test(String(line || ""));
}

function isTableStart(lines, index) {
  const header = String(lines[index] || "");
  const separator = String(lines[index + 1] || "");
  return hasTablePipes(header) && isTableSeparator(separator);
}

function parseMarkdownTable(lines, startIndex) {
  const headers = splitTableRow(lines[startIndex]);
  const align = splitTableRow(lines[startIndex + 1]).map(tableAlign);
  const rows = [];
  let index = startIndex + 2;
  while (index < lines.length && hasTablePipes(lines[index]) && lines[index].trim()) {
    rows.push(splitTableRow(lines[index]));
    index += 1;
  }
  return {
    block: { type: "table", headers, align, rows },
    nextIndex: index,
  };
}

function hasTablePipes(line) {
  return String(line || "").includes("|");
}

function isTableSeparator(line) {
  const cells = splitTableRow(line);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell.trim()));
}

function splitTableRow(line) {
  let text = String(line || "").trim();
  if (text.startsWith("|")) text = text.slice(1);
  if (text.endsWith("|")) text = text.slice(0, -1);
  return text.split("|").map((cell) => cell.trim());
}

function tableAlign(cell) {
  const text = String(cell || "").trim();
  if (text.startsWith(":") && text.endsWith(":")) return "center";
  if (text.endsWith(":")) return "right";
  if (text.startsWith(":")) return "left";
  return "";
}

function parseInline(value, keyPrefix) {
  const text = String(value || "");
  const pattern = /(\[[^\]\n]+\]\([^)]+\)|`[^`\n]+`|\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\n]+\*)/g;
  const nodes = [];
  let lastIndex = 0;
  let match;
  let tokenIndex = 0;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(...textWithBreaks(text.slice(lastIndex, match.index), `${keyPrefix}-${tokenIndex}-text`));
    }
    const token = match[0];
    nodes.push(renderInlineToken(token, `${keyPrefix}-${tokenIndex}`));
    tokenIndex += 1;
    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) {
    nodes.push(...textWithBreaks(text.slice(lastIndex), `${keyPrefix}-${tokenIndex}-tail`));
  }
  return nodes;
}

function renderInlineToken(token, key) {
  if (token.startsWith("`") && token.endsWith("`")) {
    return <code key={key}>{token.slice(1, -1)}</code>;
  }
  if (token.startsWith("**") && token.endsWith("**")) {
    return <strong key={key}>{parseInline(token.slice(2, -2), `${key}-strong`)}</strong>;
  }
  if (token.startsWith("__") && token.endsWith("__")) {
    return <strong key={key}>{parseInline(token.slice(2, -2), `${key}-strong`)}</strong>;
  }
  if (token.startsWith("*") && token.endsWith("*")) {
    return <em key={key}>{parseInline(token.slice(1, -1), `${key}-em`)}</em>;
  }
  const link = token.match(/^\[([^\]\n]+)\]\(([^)]+)\)$/);
  if (link) {
    const href = link[2].trim();
    return (
      <a key={key} href={href} target="_blank" rel="noreferrer">
        {parseInline(link[1], `${key}-link`)}
      </a>
    );
  }
  return token;
}

function textWithBreaks(text, keyPrefix) {
  const parts = String(text || "").split("\n");
  return parts.flatMap((part, index) => {
    if (index === 0) return [part];
    return [<br key={`${keyPrefix}-br-${index}`} />, part];
  });
}
