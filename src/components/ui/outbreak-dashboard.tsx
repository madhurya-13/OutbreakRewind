import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, CircleDot, GitBranch, ShieldCheck } from 'lucide-react'
import type { Investigation } from '@/api'
import { chartData, contradictions, events, evidence } from '@/data'

type OutbreakDashboardProps = {
  investigations: Investigation[]
  summary: Record<string, number>
  connected: boolean
}

const nf = new Intl.NumberFormat('en-US')

const sections = [
  { id: 'brief', index: '00', label: 'Brief' },
  { id: 'signal', index: '01', label: 'Signal' },
  { id: 'evidence', index: '02', label: 'Evidence' },
  { id: 'chronology', index: '03', label: 'Chronology' },
  { id: 'hypotheses', index: '04', label: 'Hypotheses' },
  { id: 'review', index: '05', label: 'Review' },
]

const assessment = [
  {
    title: 'Shared exposure at the North Quay depot',
    category: 'Shared location exposure',
    label: 'Partially supported',
    detail: '2 supporting · 1 contradicting · 3 pending review',
    tone: 'warm',
  },
  {
    title: 'Household contact chain from the index case',
    category: 'Person-to-person contact',
    label: 'Mixed evidence',
    detail: '2 supporting · 1 contradicting · 1 pending review',
    tone: 'mixed',
  },
  {
    title: 'Multiple independent introductions',
    category: 'Multiple independent sources',
    label: 'Insufficient information',
    detail: '1 supporting · 0 contradicting · 3 pending review',
    tone: 'quiet',
  },
]

export function OutbreakDashboard({ investigations, summary, connected }: OutbreakDashboardProps) {
  const [progress, setProgress] = useState(0)
  const [activeSection, setActiveSection] = useState('brief')
  const rootRef = useRef<HTMLDivElement | null>(null)

  const activeInvestigation = investigations[0]
  const stats = useMemo(() => [
    { label: 'Active investigations', value: summary.active_investigations ?? investigations.length ?? 1, note: 'Project Orion workspace' },
    { label: 'Cases in scope', value: summary.total_cases ?? 124, note: 'Synthetic line list' },
    { label: 'Evidence records', value: summary.evidence_records ?? 386, note: 'Source-backed entries' },
    { label: 'Open contradictions', value: summary.unresolved_contradictions ?? 12, note: 'Awaiting investigator review' },
    { label: 'Active hypotheses', value: summary.active_hypotheses ?? 18, note: 'Competing explanations' },
  ], [investigations.length, summary])

  useEffect(() => {
    let frame = 0
    const update = () => {
      frame = 0
      const doc = document.documentElement
      const max = doc.scrollHeight - window.innerHeight
      setProgress(max > 0 ? Math.min(1, window.scrollY / max) : 0)
      const root = rootRef.current
      if (!root) return
      let current = 'brief'
      root.querySelectorAll<HTMLElement>('[data-section]').forEach(section => {
        if (section.getBoundingClientRect().top <= window.innerHeight * 0.38) current = section.id
      })
      setActiveSection(current)
    }
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(update)
    }
    update()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      if (frame) window.cancelAnimationFrame(frame)
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
  }, [])

  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    const revealItems = Array.from(root.querySelectorAll<HTMLElement>('[data-reveal]'))
    if (!('IntersectionObserver' in window)) {
      revealItems.forEach(item => item.classList.add('is-in'))
      return
    }
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) entry.target.classList.add('is-in')
      })
    }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' })
    revealItems.forEach(item => observer.observe(item))

    return () => {
      observer.disconnect()
    }
  }, [])

  return <div className="ord-dashboard" ref={rootRef}>
    <div className="ord-progress" style={{ transform: `scaleX(${progress})` }} aria-hidden />
    <nav className="ord-rail" aria-label="Dashboard sections">
      {sections.map(section => <a
        key={section.id}
        href={`#${section.id}`}
        className={activeSection === section.id ? 'is-active' : undefined}
        aria-current={activeSection === section.id ? 'location' : undefined}
      >
        <span>{section.index}</span>
        <i />
        <b>{section.label}</b>
      </a>)}
    </nav>

    <section className="ord-hero" id="brief" data-section>
      <div className="ord-topline">
        <span>OUTBREAK REWIND / INVESTIGATION COMMAND CENTER</span>
        <span className="ord-topline-mid">PROJECT ORION · ORION-001</span>
        <span className={connected ? 'ord-status is-live' : 'ord-status'}><i />{connected ? 'BACKEND CONNECTED' : 'SYNTHETIC DEMO DATA'}</span>
      </div>

      <div className="ord-hero-grid">
        <div className="ord-hero-copy">
          <p className="ord-kicker"><span>REASONING / 01</span> SYNTHETIC PUBLIC-HEALTH INVESTIGATION</p>
          <h1>
            <span>Outbreak</span>
            <em>Rewind</em>
          </h1>
          <p className="ord-deck">
            A working surface for reconstructing evidence, tracing connections, and holding competing
            explanations in view. Not a verdict. A record of how the investigation thinks.
          </p>
          <div className="ord-hero-actions">
            <Link to="/hypotheses" className="ord-btn ord-btn-solid">Open hypothesis lab <ArrowUpRight size={15} /></Link>
            <Link to="/evidence" className="ord-btn">Enter evidence vault <ArrowUpRight size={15} /></Link>
          </div>
        </div>

        <div className="ord-bloom" aria-hidden>
          <div className="ord-bloom-halo" />
          <svg viewBox="0 0 600 600" className="ord-bloom-svg" role="presentation">
            <defs>
              <radialGradient id="ord-glow" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#ff5a48" stopOpacity="0.42" />
                <stop offset="52%" stopColor="#9e1017" stopOpacity="0.16" />
                <stop offset="100%" stopColor="#080706" stopOpacity="0" />
              </radialGradient>
              <linearGradient id="ord-petal" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#ffd2c9" />
                <stop offset="22%" stopColor="#ff6757" />
                <stop offset="58%" stopColor="#c2141c" />
                <stop offset="100%" stopColor="#5c0509" />
              </linearGradient>
              <linearGradient id="ord-petal-dark" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#f87364" stopOpacity="0.92" />
                <stop offset="100%" stopColor="#74070c" stopOpacity="0.2" />
              </linearGradient>
              <filter id="ord-soft" x="-30%" y="-30%" width="160%" height="160%">
                <feGaussianBlur stdDeviation="7" />
              </filter>
            </defs>
            <circle cx="300" cy="300" r="280" fill="url(#ord-glow)" />
            <g className="ord-bloom-orbits" fill="none" stroke="#f15b4f" strokeWidth="0.8">
              <circle cx="300" cy="300" r="238" strokeDasharray="2 10" opacity="0.38" />
              <circle cx="300" cy="300" r="196" opacity="0.18" />
              <circle cx="300" cy="300" r="132" strokeDasharray="1 6" opacity="0.32" />
            </g>
            <g className="ord-bloom-petals">
              {Array.from({ length: 12 }).map((_, i) => <path
                key={i}
                d="M300 300 C 318 236, 350 154, 402 112 C 394 190, 366 268, 312 312 Z"
                fill={i % 3 === 0 ? 'url(#ord-petal)' : 'url(#ord-petal-dark)'}
                stroke="#ff9f93"
                strokeWidth="0.7"
                opacity={i % 2 === 0 ? 0.95 : 0.68}
                transform={`rotate(${i * 30} 300 300)`}
              />)}
            </g>
            <g className="ord-bloom-stamens" fill="none" stroke="#ffb0a1" strokeLinecap="round">
              {Array.from({ length: 12 }).map((_, i) => <path
                key={i}
                d="M300 300 C 326 244, 388 214, 446 206"
                strokeWidth={i % 2 === 0 ? 1.5 : 1}
                opacity="0.8"
                transform={`rotate(${i * 30 + 15} 300 300)`}
              />)}
              {Array.from({ length: 12 }).map((_, i) => <circle
                key={i}
                cx="446"
                cy="206"
                r="3.2"
                fill="#ffc4b7"
                stroke="none"
                opacity="0.9"
                transform={`rotate(${i * 30 + 15} 300 300)`}
              />)}
            </g>
            <circle cx="300" cy="300" r="19" fill="#160405" stroke="#ff7a68" strokeWidth="1.2" />
            <circle cx="300" cy="300" r="7" fill="#ff6b58" filter="url(#ord-soft)" />
            <g fill="#f3b4a5" fontFamily="DM Mono, monospace" fontSize="9" letterSpacing="1.5">
              <text x="36" y="304">LOC-01</text>
              <text x="474" y="304">EXPOSURE</text>
            </g>
            <g stroke="#f05b4f" strokeWidth="0.7" opacity="0.56">
              <path d="M30 300H82M518 300H570M300 30V58M300 542V570" />
            </g>
          </svg>
          <span className="ord-bloom-caption">FIG. 01 — CONTACT TRACE, PROJECTED</span>
        </div>
      </div>

      <div className="ord-hero-foot">
        <div className="ord-scroll-cue"><span>SCROLL TO RECONSTRUCT</span><i /></div>
        <div className="ord-hero-meta">
          <span>{activeInvestigation?.investigation_name ?? 'Project Orion'}</span>
          <span>{activeInvestigation?.outbreak_category ?? 'Respiratory'} cluster</span>
          <span>Fictional data only</span>
        </div>
      </div>
    </section>

    <section className="ord-section" id="signal" data-section>
      <div className="ord-section-head" data-reveal>
        <span className="ord-index">01 / SIGNAL</span>
        <div>
          <h2>The outbreak is not the only thing spreading.</h2>
          <p>Records, revisions, and competing explanations move together. This view keeps the evidence
            position legible before anyone reaches a conclusion.</p>
        </div>
      </div>

      <div className="ord-stat-grid" data-reveal>
        {stats.map((stat, i) => <article className="ord-stat" key={stat.label}>
          <span className="ord-stat-index">{String(i + 1).padStart(2, '0')}</span>
          <strong>{nf.format(stat.value)}</strong>
          <h3>{stat.label}</h3>
          <p>{stat.note}</p>
        </article>)}
      </div>

      <div className="ord-signal-lower" data-reveal>
        <div className="ord-spark">
          <div className="ord-spark-head">
            <span>EVIDENCE SUBMISSIONS / LAST 7 DAYS</span>
            <span>SYNTHETIC SERIES</span>
          </div>
          <div className="ord-bars" aria-label="Evidence submissions over the last seven days">
            {chartData.map((point, i) => <div className="ord-bar-col" key={point.day}>
              <span className="ord-bar-value">{point.records}</span>
              <i style={{ height: `${Math.max(8, (point.records / 100) * 100)}%`, transitionDelay: `${i * 60}ms` }} />
              <b>{point.day}</b>
            </div>)}
          </div>
        </div>
        <div className="ord-note-card">
          <span className="ord-note-label">INVESTIGATOR'S NOTE</span>
          <p>“A count is not a conclusion. The assessment only becomes useful when the source behind it
            can be inspected, challenged, and revisited.”</p>
          <span className="ord-note-by">PROJECT ORION / EVIDENCE PROTOCOL</span>
        </div>
      </div>
    </section>

    <section className="ord-section ord-section-alt" id="evidence" data-section>
      <div className="ord-section-head" data-reveal>
        <span className="ord-index">02 / EVIDENCE</span>
        <div>
          <h2>Every claim keeps its receipt.</h2>
          <p>Documents are ingested, normalized, and linked back to the exact record that supports them.
            The dashboard shows the state of the ledger, not a black-box answer.</p>
        </div>
      </div>

      <div className="ord-evidence-grid">
        <div className="ord-ledger" data-reveal>
          <div className="ord-ledger-head"><span>RECORD</span><span>TYPE</span><span>SOURCE</span><span>STATUS</span></div>
          {evidence.map((item, i) => <Link to="/evidence" className="ord-ledger-row" key={item.id}>
            <span><b>{item.id}</b><small>0{i + 1} / 04</small></span>
            <span>{item.type}</span>
            <span>{item.source}</span>
            <span className={`ord-state ${item.status === 'Verified' ? 'is-verified' : 'is-pending'}`}>{item.status}</span>
          </Link>)}
          <Link to="/evidence" className="ord-text-link">Inspect the full evidence vault <ArrowUpRight size={14} /></Link>
        </div>

        <aside className="ord-source-card" data-reveal>
          <div className="ord-source-mark"><ShieldCheck size={17} /><span>PROVENANCE FIRST</span></div>
          <p>Each link is stored with its source type, original reference, extraction method, and a
            snapshot of the values at the time of linking.</p>
          <div className="ord-source-list">
            <span><CircleDot size={12} /> Hash-checked uploads</span>
            <span><CircleDot size={12} /> Record-level verification</span>
            <span><CircleDot size={12} /> Append-only review history</span>
          </div>
          <span className="ord-mono">EVIDENCE / {nf.format(stats[2].value)} RECORDS / ORION-001</span>
        </aside>
      </div>
    </section>

    <section className="ord-section" id="chronology" data-section>
      <div className="ord-section-head" data-reveal>
        <span className="ord-index">03 / CHRONOLOGY</span>
        <div>
          <h2>Time is a source, too.</h2>
          <p>Reconstructed events preserve the original wording and the uncertainty around every date.
            The timeline below is a reading aid, not a definitive sequence.</p>
        </div>
      </div>

      <div className="ord-chronology" data-reveal>
        <div className="ord-chronology-head"><span>JUN 2024</span><span>RECONSTRUCTED EVENT</span><span>CLASSIFICATION</span></div>
        {events.slice(0, 3).map((event, i) => <Link to="/timeline" className="ord-event-row" key={event.id}>
          <span className="ord-event-date"><b>{event.date.slice(-2)}</b><small>{event.date.slice(5, 7)} / 2024</small></span>
          <span className="ord-event-line"><i className={`is-${event.severity}`} /></span>
          <span className="ord-event-copy"><b>{event.title}</b><small>{event.summary}</small></span>
          <span className="ord-event-tag">{event.category}</span>
          <ArrowUpRight size={14} />
        </Link>)}
        <div className="ord-chronology-foot">
          <span><GitBranch size={14} /> Deterministic reconstruction / source-level traceability</span>
          <Link to="/timeline" className="ord-text-link">Open the timeline <ArrowUpRight size={14} /></Link>
        </div>
      </div>
    </section>

    <section className="ord-section ord-section-alt" id="hypotheses" data-section>
      <div className="ord-section-head" data-reveal>
        <span className="ord-index">04 / HYPOTHESES</span>
        <div>
          <h2>Three explanations. No winner.</h2>
          <p>Hypotheses are entered by investigators and judged against linked, reviewed evidence. The
            system can show the shape of the support; it cannot choose the answer.</p>
        </div>
      </div>

      <div className="ord-hypo-grid" data-reveal>
        {assessment.map((item, i) => <article className={`ord-hypo tone-${item.tone}`} key={item.title}>
          <span className="ord-hypo-num">0{i + 1}</span>
          <span className="ord-hypo-cat">{item.category}</span>
          <h3>{item.title}</h3>
          <div className="ord-hypo-rule" />
          <span className="ord-hypo-label">{item.label}</span>
          <p>{item.detail}</p>
        </article>)}
      </div>
      <div className="ord-hypo-foot" data-reveal>
        <p><b>Qualitative by design.</b> No probabilities, percentages, or automatic winning hypothesis.
          Strength and source reliability are assessed independently.</p>
        <Link to="/hypotheses" className="ord-btn">Enter the hypothesis lab <ArrowUpRight size={15} /></Link>
      </div>
    </section>

    <section className="ord-section ord-review" id="review" data-section>
      <div className="ord-section-head" data-reveal>
        <span className="ord-index">05 / REVIEW</span>
        <div>
          <h2>What still needs a human.</h2>
          <p>Contradictions and pending links are review prompts. They stay visible until an investigator
            records a decision and a reason.</p>
        </div>
      </div>

      <div className="ord-review-grid" data-reveal>
        <div>
          {contradictions.map((item, i) => <article className="ord-review-row" key={item.id}>
            <span className="ord-review-index">0{i + 1}</span>
            <div>
              <b>{item.title}</b>
              <small>{item.description}</small>
            </div>
            <span className={`ord-pill is-${item.severity}`}>{item.severity}</span>
            <span className="ord-review-status">{item.status}</span>
          </article>)}
          <Link to="/contradictions" className="ord-text-link">Open contradiction center <ArrowUpRight size={14} /></Link>
        </div>
        <aside className="ord-review-count">
          <span>REVIEW QUEUE</span>
          <strong>{nf.format(summary.requiring_review ?? 39)}</strong>
          <p>items connecting evidence, assessment, and investigator action.</p>
          <div><span>IMPACT</span><b>{summary.pending_impact_records ?? 31}</b></div>
          <div><span>LINKS</span><b>{summary.pending_evidence_links ?? 8}</b></div>
        </aside>
      </div>
    </section>

    <footer className="ord-footer">
      <div className="ord-footer-word" aria-hidden>ORION</div>
      <div className="ord-footer-grid">
        <div>
          <span className="ord-mono">OUTBREAK REWIND / PROJECT ORION</span>
          <p>Synthetic investigation data for demonstration and evaluation. This console supports
            investigators; it does not make clinical or epidemiological decisions.</p>
        </div>
        <div className="ord-footer-links">
          <Link to="/investigations">Investigations</Link>
          <Link to="/network">Case network</Link>
          <Link to="/reports">Reports</Link>
          <Link to="/settings">Settings</Link>
        </div>
        <span className="ord-mono ord-footer-right">ORION-001<br />MMXXVI</span>
      </div>
    </footer>
  </div>
}
