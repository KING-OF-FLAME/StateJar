import { Link } from 'react-router-dom'
import { PIPELINE_STAGES } from '../components/Pipeline.jsx'

/* About.

   Content rules this page is held to, and the reason each exists:
     - no metric that has not been measured. There is no accuracy benchmark
       yet, so no accuracy number appears here.
     - no "industry-leading" / "revolutionary" / "cutting-edge".
     - every claim demonstrable in the product inside thirty seconds. The
       cross-domain examples below are real extractor output, not illustrations.
     - comparisons to other systems are accurate and generous about theirs. */

const STAGE_LINES = {
  ingest: 'The message arrives. Nothing has been trusted yet.',
  extract: 'Three tiers, cheapest first, propose fields. Rules, then a small neural model, then — only on messy input — a language model.',
  canonicalize: 'Each proposal is type-checked, normalized, and routed to exactly one path. This is where a guess is refused.',
  handle: 'The state is serialised with keys sorted at every level and hashed. Same bytes in, same handle out.',
  store: 'The new state is appended as a child of the previous one. Nothing is ever rewritten.',
  retrieve: 'A question selects the minimum set of fields that answers it. Not the state — a subset of it.',
  audit: 'What was disclosed, from which handle, to which model, is written down and can be replayed.',
}

// Real extractor output, produced by running these exact sentences through the
// rules tier. Nothing here was written by hand.
const DOMAINS = [
  { field: 'Beekeeping', said: 'Hive inspection interval is 9 days.',
    stored: 'dynamic.hive_inspection_interval', value: 'duration · 777600 s' },
  { field: 'Ceramics', said: 'Kiln firing time is 14 hours.',
    stored: 'dynamic.kiln_firing_time', value: 'duration · 50400 s' },
  { field: 'Fisheries', said: 'Net mesh size is 40 mm.',
    stored: 'dynamic.net_mesh_size', value: 'quantity · 40 mm' },
  { field: 'Dialysis', said: 'Dialysis session length is 4 hours.',
    stored: 'dynamic.dialysis_session_length', value: 'duration · 14400 s' },
]

const GUARANTEES = [
  { title: 'It refuses to guess',
    body: `A value has to pass a type check before it enters a field. "24 tonnes"
      classifies as a quantity, and a money field will not take a quantity — so it
      is declined, not coerced. Every decline is recorded with a reason and shown
      to the user. Storing less is the deliberate cost of never storing something
      wrong and quiet.` },
  { title: 'One field, one value',
    body: `A concept resolves to exactly one path, so two values for it cannot
      both be current. When you change your mind the old value moves to history
      and the new one takes the field. The model is never shown both, which makes
      answering from a superseded value impossible rather than unlikely.` },
  { title: 'Portable and verifiable',
    body: `Every state resolves to a handle computed from its own canonical
      bytes. The same state always produces the same handle, and restoring one
      re-derives it and refuses if they disagree. Open a handle in a different
      session, a different model, a different vendor — it is data, not a feature
      of somebody's product.` },
]

const GAPS = [
  { title: 'No published accuracy benchmark',
    body: `There is a golden corpus in the test suite and it passes, but no
      measured extraction accuracy against a public dataset, and therefore no
      number quoted anywhere on this page. Until that exists, treat claims about
      how much StateJar catches — including ours — as unmeasured.` },
  { title: 'Concept merging depends on the tier that ran',
    body: `Two names for one concept are merged by content-word overlap, not by
      embeddings, because dynamic concepts are hashed and the merge therefore has
      to be deterministic. Names that share no words — "lorry limit" and "truck
      capacity" — are not merged by the deterministic tiers. The language tier
      often catches it. Without a key, it does not.` },
  { title: 'Recall on long multi-fact messages is untested',
    body: `A message carrying six or eight facts at once has not been measured
      for how many are recovered. The demo turns are deliberately one or two
      facts each, which is a fair reflection of what has been verified and not of
      what a real user types.` },
  { title: 'Unclaimed money defaults to the budget field',
    body: `A money value in a clause naming no recognised money concept currently
      lands in constraints.budget.max. The vocabulary is literal rather than
      stemmed, so "cost" is recognised and "costs" is not. Known, reproduced,
      and not yet fixed — the honest fix is to fail closed instead of defaulting,
      which is a change to routing behaviour.` },
  { title: 'Chat history is per browser',
    body: `Raw transcripts are never stored server-side, so the conversation
      lives only in the browser that typed it. Sign in elsewhere and the memory
      is all there and the conversation is not. This is a consequence of the
      design rather than a defect, but it surprises people, so it belongs here.` },
]

export default function About() {
  return (
    <div className="about-page">
      <section className="about-hero">
        <p className="section-kicker">About StateJar</p>
        <h1 className="about-one-liner">
          A memory layer for conversational AI that refuses to guess, records why
          it refused, and turns everything it remembers into a portable handle
          you can open in any model.
        </h1>
      </section>

      <section className="about-block">
        <h2>The problem</h2>
        <p>
          A shipping assistant is told <em>“max load per container is 24
          tonnes”</em>. It stores a budget of twenty-four rupees. For the rest of
          the conversation it quotes that budget back — confidently, in the right
          format, in the right place. It never says it guessed, because it does
          not know it did.
        </p>
        <p>
          This is not a bug in one product. Any memory built on similarity
          matching has this failure mode: “max load” looks like a limit, a limit
          looks like a budget, and a number is a number. The matching succeeded.
          Nothing anywhere in the pipeline asked whether <em>tonnes</em> can be
          money.
        </p>
        <p className="about-emphasis">
          The dangerous part is not the error. It is that the system reports the
          same confidence whether it was right or wrong, so the person least able
          to detect the mistake is the one who has to.
        </p>
      </section>

      <section className="about-block">
        <h2>What StateJar does about it</h2>
        <div className="about-guarantees">
          {GUARANTEES.map((g) => (
            <div className="about-guarantee" key={g.title}>
              <h3>{g.title}</h3>
              <p>{g.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="about-block">
        <h2>How it works</h2>
        <p className="about-sub">
          Seven stages, and you can watch all seven run on a real message in the{' '}
          <Link to="/playground">Playground</Link>.
        </p>
        <ol className="about-pipeline">
          {PIPELINE_STAGES.map((s, i) => (
            <li key={s.key} className="about-stage">
              <span className="about-stage-n mono">{i + 1}</span>
              <span className="about-stage-name">{s.label}</span>
              <span className="about-stage-line">{STAGE_LINES[s.key]}</span>
            </li>
          ))}
        </ol>
        <p className="about-note">
          The order is the whole argument. Extraction runs <em>before</em>
          {' '}canonicalization, so a probabilistic tier can only ever
          <em> propose</em>; the deterministic layer decides. That is why a
          language model in the pipeline does not make the pipeline
          probabilistic.
        </p>
      </section>

      <section className="about-block">
        <h2>No domain code</h2>
        <p>
          StateJar has never been taught what a beekeeping field, a kiln
          schedule or a freight manifest looks like. There is no industry
          vocabulary, no ontology, no per-domain configuration. It works because
          it hardcodes what a <strong>value</strong> can be — money, quantity,
          date, duration, identifier — and not what a <strong>field</strong> can
          be called.
        </p>
        <div className="about-domains">
          {DOMAINS.map((d) => (
            <div className="about-domain" key={d.field}>
              <p className="about-domain-tag mono">{d.field}</p>
              <p className="about-domain-said">“{d.said}”</p>
              <p className="about-domain-stored mono">{d.stored}</p>
              <p className="about-domain-value mono">{d.value}</p>
            </div>
          ))}
        </div>
        <p className="about-note">
          Real output from the rules tier on those four sentences — no model, no
          network, and no line of code anywhere that knows what a hive is. Each
          became a field named after what you called it, holding a value typed
          and converted to a base unit.
        </p>
      </section>

      <section className="about-block">
        <h2>Where this matters</h2>
        <p>
          Healthcare intake. Benefits and welfare applications. Legal aid.
          Disaster response. What these share is that a misremembered number
          reaches someone who cannot check it — an applicant who does not know
          what the caseworker’s screen says, a patient who does not know what was
          written down.
        </p>
        <p>
          An assistant that says <em>“I did not store that, and here is why”</em>
          {' '}is more useful in those settings than one that is right more often
          and quiet when it is wrong. The first can be corrected. The second
          cannot, because nobody knows there is anything to correct.
        </p>
      </section>

      <section className="about-block">
        <h2>Status</h2>
        <ul className="about-status">
          <li>
            <strong>Indian Utility Patent 202621017626</strong> — filed.
          </li>
          <li>
            <strong>Deployed</strong> at statejar.com, with the console, the API
            and both demos running on a live instance.
          </li>
          <li>
            <strong>Built by Team Hello World</strong> for Hack4Humanity 2026.
          </li>
          <li>
            <strong>Test suite:</strong> the full backend suite runs on every
            change, and documentation coverage is enforced by it — a new
            endpoint, setting, provider or decline reason fails the build until
            it has a <Link to="/help">help entry</Link>.
          </li>
        </ul>
      </section>

      <section className="about-block about-gaps">
        <h2>What doesn’t work yet</h2>
        <p className="about-sub">
          Kept on the page rather than in a footnote. If one of these rules
          StateJar out for what you are building, better to find it here.
        </p>
        {GAPS.map((g) => (
          <div className="about-gap" key={g.title}>
            <h3>{g.title}</h3>
            <p>{g.body}</p>
          </div>
        ))}
      </section>

      <section className="about-block about-cta">
        <h2>See it rather than read about it</h2>
        <p>
          The <Link to="/playground">Playground</Link> runs the whole pipeline
          without a provider key — send one message and watch the seven stages,
          or run the 17-turn demo. The{' '}
          <Link to="/help">help centre</Link> explains every control, chip and
          decline reason in it.
        </p>
      </section>
    </div>
  )
}
