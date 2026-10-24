import React from 'react';
import ReactMarkdown from 'react-markdown';
import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import bash from 'react-syntax-highlighter/dist/esm/languages/prism/bash';
import c from 'react-syntax-highlighter/dist/esm/languages/prism/c';
import cpp from 'react-syntax-highlighter/dist/esm/languages/prism/cpp';
import csharp from 'react-syntax-highlighter/dist/esm/languages/prism/csharp';
import css from 'react-syntax-highlighter/dist/esm/languages/prism/css';
import diff from 'react-syntax-highlighter/dist/esm/languages/prism/diff';
import go from 'react-syntax-highlighter/dist/esm/languages/prism/go';
import java from 'react-syntax-highlighter/dist/esm/languages/prism/java';
import javascript from 'react-syntax-highlighter/dist/esm/languages/prism/javascript';
import json from 'react-syntax-highlighter/dist/esm/languages/prism/json';
import jsx from 'react-syntax-highlighter/dist/esm/languages/prism/jsx';
import kotlin from 'react-syntax-highlighter/dist/esm/languages/prism/kotlin';
import markdown from 'react-syntax-highlighter/dist/esm/languages/prism/markdown';
import markup from 'react-syntax-highlighter/dist/esm/languages/prism/markup';
import php from 'react-syntax-highlighter/dist/esm/languages/prism/php';
import python from 'react-syntax-highlighter/dist/esm/languages/prism/python';
import ruby from 'react-syntax-highlighter/dist/esm/languages/prism/ruby';
import rust from 'react-syntax-highlighter/dist/esm/languages/prism/rust';
import sql from 'react-syntax-highlighter/dist/esm/languages/prism/sql';
import tsx from 'react-syntax-highlighter/dist/esm/languages/prism/tsx';
import typescript from 'react-syntax-highlighter/dist/esm/languages/prism/typescript';
import yaml from 'react-syntax-highlighter/dist/esm/languages/prism/yaml';
import { CopyButton } from './ui';

// Only common languages are bundled; others render as plain text.
const LANGUAGES = {
  bash, c, cpp, csharp, css, diff, go, java, javascript, json, jsx, kotlin,
  markdown, markup, php, python, ruby, rust, sql, tsx, typescript, yaml,
};
Object.entries(LANGUAGES).forEach(([name, def]) => SyntaxHighlighter.registerLanguage(name, def));

const ALIASES = {
  py: 'python', js: 'javascript', ts: 'typescript', sh: 'bash', shell: 'bash', zsh: 'bash',
  yml: 'yaml', html: 'markup', xml: 'markup', cs: 'csharp', 'c++': 'cpp', rb: 'ruby',
  kt: 'kotlin', md: 'markdown', rs: 'rust',
};

export function CodeBlock({ language, code }) {
  const lang = ALIASES[language] || language;
  return (
    <div className="codeblock">
      <div className="codeblock-head">
        <span>{language || 'text'}</span>
        <CopyButton text={code} />
      </div>
      <SyntaxHighlighter language={LANGUAGES[lang] ? lang : 'text'} style={oneDark} PreTag="pre">
        {code}
      </SyntaxHighlighter>
    </div>
  );
}

const components = {
  // react-markdown v9 has no `inline` flag: fenced blocks carry a language
  // class or span multiple lines; everything else is inline code.
  pre: ({ children }) => <>{children}</>,
  code({ className, children }) {
    const text = String(children);
    const match = /language-([\w+-]+)/.exec(className || '');
    if (match || text.includes('\n')) {
      return <CodeBlock language={match?.[1]} code={text.replace(/\n$/, '')} />;
    }
    return <code>{children}</code>;
  },
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
  ),
};

export default function Markdown({ children }) {
  return (
    <div className="md">
      <ReactMarkdown components={components}>{children || ''}</ReactMarkdown>
    </div>
  );
}
