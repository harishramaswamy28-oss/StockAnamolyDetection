import React from 'react'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <main className="app-error" role="alert">
          <h1>The dashboard hit a display error</h1>
          <p>{this.state.error.message || 'An unexpected error stopped this view.'}</p>
          <button className="primary" onClick={() => window.location.reload()}>Reload dashboard</button>
        </main>
      )
    }
    return this.props.children
  }
}
