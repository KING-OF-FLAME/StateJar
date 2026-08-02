import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/* Assistant replies are markdown, and were being rendered as raw text — so a
 * list came out as "- email - 15 August - ₹2500" run together on one line,
 * which is exactly the reply that matters most: the one confirming several
 * remembered values back to the user.
 *
 * Only the elements the system prompt's formatting contract asks for are
 * mapped. Anything else falls through to react-markdown's default, and raw
 * HTML is not enabled — a model reply is untrusted input.
 */
export default function Markdown({ children, className = '' }) {
  return (
    <div className={`md ${className}`.trim()}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // the bubble is already a block; a nested <p> would double its margins
          p: ({ children }) => <p className="md-p">{children}</p>,
          ul: ({ children }) => <ul className="md-ul">{children}</ul>,
          ol: ({ children }) => <ol className="md-ol">{children}</ol>,
          li: ({ children }) => <li className="md-li">{children}</li>,
          strong: ({ children }) => <strong className="md-strong">{children}</strong>,
          code: ({ inline, children }) =>
            inline
              ? <code className="md-code">{children}</code>
              : <pre className="md-pre"><code>{children}</code></pre>,
          a: ({ href, children }) => (
            // a model can emit any URL; never let it open with opener access
            <a href={href} target="_blank" rel="noopener noreferrer nofollow">{children}</a>
          ),
          table: ({ children }) => (
            <div className="md-table-wrap"><table>{children}</table></div>
          ),
        }}
      >
        {typeof children === 'string' ? children : ''}
      </ReactMarkdown>
    </div>
  )
}
