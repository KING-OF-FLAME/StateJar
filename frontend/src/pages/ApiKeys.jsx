import ProviderCards from '../components/ProviderCards.jsx'
import DeveloperKeys from '../components/DeveloperKeys.jsx'

export default function ApiKeys() {
  return (
    <>
      <div className="page-head">
        <div>
          <h1>API Keys</h1>
          <p className="page-sub">
            Two kinds of key: the provider keys StateJar uses on your behalf, and the
            StateJar keys your own code uses to call this API.
          </p>
        </div>
      </div>

      <ProviderCards />

      <DeveloperKeys />
    </>
  )
}
