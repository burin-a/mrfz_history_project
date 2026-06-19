import { Component } from "react"

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error("应用错误:", error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          background: "#0a0a1a",
          color: "#8892b0",
          fontFamily: "sans-serif",
        }}>
          <h2 style={{ color: "#4fc3f7", marginBottom: "8px" }}>应用遇到错误</h2>
          <p style={{ fontSize: "13px", marginBottom: "16px" }}>请刷新页面重试</p>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: "8px 24px",
              background: "rgba(79,195,247,0.1)",
              border: "1px solid rgba(79,195,247,0.25)",
              color: "#4fc3f7",
              cursor: "pointer",
              borderRadius: "4px",
            }}
          >
            刷新页面
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
