import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api.js'

/* Profile: four optional fields, and a visible way past them.

   Reached from the account menu, and once from `?onboarding` straight after
   signup. The onboarding pass must never stand between a new account and the
   Playground — the demo path is two clicks from signup and stays that way — so
   Skip is a real control, not a greyed-out afterthought. */

export const FIELDS = [
  { name: 'display_name', label: 'Display name', max: 80,
    placeholder: 'Meera Nair' },
  { name: 'organization', label: 'Organization', max: 120,
    placeholder: 'ReliefNet' },
  { name: 'role', label: 'Role', max: 80,
    placeholder: 'Operations coordinator' },
  { name: 'use_case', label: 'What are you building?', max: 400, area: true,
    placeholder: 'Field intake assistant that must not misremember numbers.' },
]

const EMPTY = Object.fromEntries(FIELDS.map((f) => [f.name, '']))

export default function Profile() {
  const [params] = useSearchParams()
  const onboarding = params.has('onboarding')
  const navigate = useNavigate()

  const [values, setValues] = useState(EMPTY)
  const [errors, setErrors] = useState({})
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api('/profile')
      .then((p) => {
        setValues(Object.fromEntries(
          FIELDS.map((f) => [f.name, p[f.name] || ''])))
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const set = (name, v) => {
    setValues((prev) => ({ ...prev, [name]: v }))
    // clear this field's server error the moment it is edited; leaving it
    // under a field the user has already changed just reads as broken
    setErrors((prev) => (prev[name] ? { ...prev, [name]: undefined } : prev))
  }

  const save = async (e) => {
    e?.preventDefault()
    setSaving(true)
    setErrors({})
    setError('')
    setNotice('')
    try {
      // send every field: a cleared box means "remove this", which the API
      // reads from an explicit empty value rather than from an absent key
      await api('/profile', { method: 'PATCH', body: values })
      setNotice('Saved.')
      if (onboarding) navigate('/playground')
    } catch (err) {
      /* The API rejects rather than coerces, and says which field and why.
         Surfacing that verbatim beside the input is the whole point — a bare
         "invalid input" would make the user guess at the rule. */
      const fields = err.detail?.fields
      if (fields && typeof fields === 'object') setErrors(fields)
      else setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <p className="empty-note">Loading…</p>

  return (
    <div className="prof-page">
      <header className="prof-head">
        <h1>{onboarding ? 'Tell us a little about you' : 'Profile'}</h1>
        <p className="prof-lede">
          {onboarding
            ? 'Optional, and you can change it later. Skip it and go straight to the Playground.'
            : 'Four optional fields. Nothing here is required, and none of it is sent to a model.'}
        </p>
      </header>

      {error && <p className="auth-error">{error}</p>}

      <form className="prof-form" onSubmit={save}>
        {FIELDS.map((f) => (
          <label className="prof-field" key={f.name}>
            <span className="prof-label">
              {f.label}
              <span className="prof-count mono">
                {(values[f.name] || '').length}/{f.max}
              </span>
            </span>
            {f.area ? (
              <textarea
                rows={3} value={values[f.name]} placeholder={f.placeholder}
                onChange={(e) => set(f.name, e.target.value)}
                aria-invalid={Boolean(errors[f.name])}
              />
            ) : (
              <input
                type="text" value={values[f.name]} placeholder={f.placeholder}
                onChange={(e) => set(f.name, e.target.value)}
                aria-invalid={Boolean(errors[f.name])}
              />
            )}
            {errors[f.name] && (
              <span className="prof-error" role="alert">{errors[f.name]}</span>
            )}
          </label>
        ))}

        <div className="prof-actions">
          <button className="btn btn-primary" type="submit" disabled={saving}>
            {saving ? 'Saving…' : onboarding ? 'Save and continue' : 'Save'}
          </button>
          {onboarding && (
            <button
              className="btn btn-ghost" type="button"
              onClick={() => navigate('/playground')}
            >
              Skip for now
            </button>
          )}
          {notice && <span className="prof-notice">{notice}</span>}
        </div>
      </form>
    </div>
  )
}
