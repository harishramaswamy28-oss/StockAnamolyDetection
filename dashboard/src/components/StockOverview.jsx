import React, { useState, useRef, useEffect } from 'react'

export default function StockOverview({ stocks, summaries, selectedSymbol, onSelect }) {
  const [isOpen, setIsOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const dropdownRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const filteredStocks = stocks.filter(stock =>
    stock.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
    stock.name.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const handleSelect = (symbol) => {
    onSelect(symbol)
    setIsOpen(false)
    setSearchQuery('')
  }

  const currentStock = stocks.find(s => s.symbol === selectedSymbol)
  const currentSummary = selectedSymbol ? summaries[selectedSymbol] : null
  const hasAnomalies = currentSummary && currentSummary.total_anomalies > 0

  return (
    <div className="card stock-overview-card">
      <h2>Stock Overview</h2>
      
      <div className="stock-search-wrapper" ref={dropdownRef}>
        <button
          type="button"
          className="stock-search-trigger"
          onClick={() => setIsOpen(!isOpen)}
          aria-expanded={isOpen}
          aria-haspopup="listbox"
        >
          <div className="search-selected">
            <span className="search-symbol">
              {currentStock ? currentStock.symbol : 'Select Stock'}
            </span>
            {currentStock && currentSummary && currentSummary.latest_price != null && (
              <span className="search-price">$${currentSummary.latest_price.toFixed(2)}</span>
            )}
            {hasAnomalies && (
              <span className="search-anomaly-badge">{currentSummary.total_anomalies}</span>
            )}
          </div>
          <svg className="search-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>

        {isOpen && (
          <div className="stock-search-dropdown" role="listbox">
            <div className="search-input-wrapper">
              <svg className="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input
                ref={inputRef}
                type="text"
                placeholder="Search stocks..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onFocus={() => setIsOpen(true)}
                autoFocus
              />
            </div>
            <div className="search-options" role="listbox">
              {filteredStocks.length === 0 ? (
                <div className="search-no-results">No stocks found</div>
              ) : (
                filteredStocks.map((stock) => {
                  const summary = summaries[stock.symbol]
                  const isSelected = selectedSymbol === stock.symbol
                  const stockHasAnomalies = summary && summary.total_anomalies > 0
                  return (
                    <button
                      key={stock.security_id}
                      type="button"
                      role="option"
                      aria-selected={isSelected}
                      className={`search-option${isSelected ? ' selected' : ''}`}
                      onClick={() => handleSelect(stock.symbol)}
                    >
                      <div className="option-main">
                        <span className="option-symbol">{stock.symbol}</span>
                        <span className="option-name">{stock.name}</span>
                      </div>
                      <div className="option-details">
                        {summary && summary.latest_price != null && (
                          <span className="option-price">$${summary.latest_price.toFixed(2)}</span>
                        )}
                        {stockHasAnomalies && (
                          <span className="option-anomaly-badge">{summary.total_anomalies}</span>
                        )}
                      </div>
                    </button>
                  )
                })
              )}
            </div>
          </div>
        )}
      </div>

      {stocks.length === 0 && (
        <p className="muted">No securities found. Run metadata ingestion first.</p>
      )}
    </div>
  )
}