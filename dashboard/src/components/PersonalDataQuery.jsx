import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'

const FILTER_OPERATORS = [
  ['eq', 'equals'], ['neq', 'does not equal'], ['gt', 'greater than'],
  ['gte', 'at least'], ['lt', 'less than'], ['lte', 'at most'],
  ['contains', 'contains'], ['starts_with', 'starts with'],
  ['is_null', 'is empty'], ['is_not_null', 'is not empty'],
]

const ACTION_LABELS = { retrieve: 'View records', add: 'Add a record', modify: 'Edit a record', remove: 'Remove a record' }

function buildSqlPreview({ tableName, action, columns, filters, filterLogic, sortBy, sortDirection, limit, values }) {
  const filterSql = (items, offset = 1) => {
    let parameter = offset
    const clauses = items.map(({ column, operator }) => {
      if (operator === 'is_null') return `"${column}" IS NULL`
      if (operator === 'is_not_null') return `"${column}" IS NOT NULL`
      const expression = operator === 'contains'
        ? `"${column}" ILIKE '%' || $${parameter} || '%'`
        : operator === 'starts_with'
          ? `"${column}" ILIKE $${parameter} || '%'`
          : `"${column}" ${{ eq: '=', neq: '<>', gt: '>', gte: '>=', lt: '<', lte: '<=' }[operator] || '='} $${parameter}`
      parameter += 1
      return expression
    })
    return clauses
  }

  if (action === 'retrieve') {
    const selection = columns.length ? columns.map((column) => `"${column}"`).join(', ') : '/* select at least one column */'
    const clauses = filterSql(filters, 2)
    const conditions = ['"user_id" = $1']
    if (clauses.length) conditions.push(`(${clauses.join(filterLogic === 'or' ? ' OR ' : ' AND ')})`)
    return `SELECT ${selection}\nFROM public."${tableName}"\nWHERE ${conditions.join(' AND ')}\nORDER BY "${sortBy}" ${sortDirection.toUpperCase()}\nLIMIT ${Number(limit)};`
  }

  if (action === 'add') {
    if (tableName === 'watchlist') return 'INSERT INTO public."watchlist" ("user_id", "watchlist_no", "name")\nVALUES ($current_user_id, $next_watchlist_no, $name);'
    if (tableName === 'watchlist_security') return 'INSERT INTO public."watchlist_security" ("user_id", "watchlist_no", "security_id")\nSELECT $current_user_id, w."watchlist_no", s."security_id"\nFROM public."watchlist" AS w\nJOIN public."security" AS s ON upper(s."symbol") = $symbol\nWHERE w."user_id" = $current_user_id AND w."watchlist_no" = $watchlist_no;'
    if (tableName === 'alert') return 'INSERT INTO public."alert" ("user_id", "alert_no", "security_id", "condition", "target_price", "status")\nSELECT $current_user_id, $next_alert_no, s."security_id", $condition, $target_price, \'active\'\nFROM public."security" AS s\nWHERE upper(s."symbol") = $symbol;'
  }

  if (tableName === 'user_preference' && action === 'modify') {
    const columnsToSet = ['price_alerts', 'anomaly_alerts', 'notification_mode']
    return `INSERT INTO public."user_preference" ("user_id", ${columnsToSet.map((column) => `"${column}"`).join(', ')})\nVALUES ($current_user_id, ${columnsToSet.map((column) => `$${column}`).join(', ')})\nON CONFLICT ("user_id") DO UPDATE SET ${columnsToSet.map((column) => `"${column}" = EXCLUDED."${column}"`).join(', ')};`
  }

  const target = { app_user: 'user_id', watchlist: 'watchlist_no', alert: 'alert_no', notification: 'notification_id' }[tableName]
  if (tableName === 'watchlist_security') {
    return `DELETE FROM public."watchlist_security"\nWHERE "user_id" = $current_user_id AND "watchlist_no" = $watchlist_no AND "security_id" = $security_id;`
  }
  const ownedWhere = tableName === 'app_user'
    ? '"user_id" = $current_user_id'
    : `"user_id" = $current_user_id AND "${target}" = $selected_${target}`
  if (action === 'remove') return `DELETE FROM public."${tableName}"\nWHERE ${ownedWhere};`
  if (action === 'modify') {
    const assignments = Object.keys(values).map((column) => `"${column}" = $${column}`)
    return assignments.length
      ? `UPDATE public."${tableName}"\nSET ${assignments.join(', ')}\nWHERE ${ownedWhere};`
      : `UPDATE public."${tableName}"\nSET /* choose fields to update */\nWHERE ${ownedWhere};`
  }
  return '-- Choose an available action to preview its query.'
}

function editableFields(table, action) {
  const fields = {
    app_user: { modify: [['name', 'Your name', 'text'], ['email', 'Email', 'email']] },
    watchlist: { add: [['name', 'Watchlist name', 'text']], modify: [['name', 'New watchlist name', 'text']] },
    watchlist_security: { add: [['watchlist_no', 'Your watchlist', 'watchlist'], ['symbol', 'Security symbol', 'symbol']] },
    alert: {
      add: [['symbol', 'Security symbol', 'symbol'], ['condition', 'Condition', 'condition'], ['target_price', 'Target price', 'number']],
      modify: [['condition', 'Condition', 'condition'], ['target_price', 'Target price', 'number'], ['status', 'Status', 'alert_status']],
    },
    notification: { modify: [['status', 'Notification status', 'notification_status']] },
    user_preference: { modify: [['price_alerts', 'Price alerts enabled', 'boolean'], ['anomaly_alerts', 'Anomaly alerts enabled', 'boolean'], ['notification_mode', 'Notification mode', 'notification_mode']] },
  }
  return fields[table]?.[action] || []
}

export default function PersonalDataQuery({ userId, watchlists = [], alerts = [], notifications = [], onChanged, onAccountUpdated }) {
  const [schema, setSchema] = useState(null)
  const [tableName, setTableName] = useState('watchlist')
  const [action, setAction] = useState('retrieve')
  const [columns, setColumns] = useState([])
  const [filters, setFilters] = useState([])
  const [filterLogic, setFilterLogic] = useState('and')
  const [values, setValues] = useState({})
  const [sortBy, setSortBy] = useState('watchlist_no')
  const [sortDirection, setSortDirection] = useState('desc')
  const [limit, setLimit] = useState(50)
  const [rows, setRows] = useState(null)
  const [message, setMessage] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.getPersonalQuerySchema()
      .then((data) => setSchema(data))
      .catch((err) => setError(err.message))
  }, [userId])

  const activeTable = useMemo(() => schema?.tables.find((item) => item.name === tableName) || null, [schema, tableName])
  const actions = activeTable?.actions || []
  const fields = editableFields(tableName, action)
  const sqlPreview = activeTable ? buildSqlPreview({
    tableName, action, columns, filters, filterLogic, sortBy, sortDirection, limit, values,
  }) : ''

  const reset = (nextTable, nextAction) => {
    setFilters([])
    setValues({})
    setRows(null)
    setMessage(null)
    setError(null)
    const table = schema?.tables.find((item) => item.name === nextTable)
    if (table) {
      setColumns(table.columns.map((column) => column.name))
      setSortBy(table.default_sort)
    }
    setTableName(nextTable)
    setAction(nextAction)
  }

  useEffect(() => {
    const table = schema?.tables.find((item) => item.name === tableName)
    if (table && columns.length === 0) setColumns(table.columns.map((column) => column.name))
  }, [schema, tableName, columns.length])

  const run = async (event) => {
    event.preventDefault()
    setError(null)
    setMessage(null)
    setBusy(true)
    try {
      const data = await api.runPersonalQuery({
        table: tableName,
        action,
        columns: action === 'retrieve' ? columns : [],
        filters: filters.map((filter) => ({
          ...filter,
          value: ['is_null', 'is_not_null'].includes(filter.operator) ? null : filter.value,
        })),
        filter_logic: filterLogic,
        values,
        sort_by: sortBy,
        sort_direction: sortDirection,
        limit: Number(limit),
      })
      if (action === 'retrieve') {
        setRows(data.rows)
        setMessage(`${data.row_count} of your records returned.`)
      } else {
        setRows(null)
        setMessage(data.message || 'Your change was saved.')
        setFilters([])
        setValues({})
        await onChanged?.()
        if (tableName === 'app_user') await onAccountUpdated?.()
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (!schema && !error) return <section className="card"><p className="muted">Loading safe query options…</p></section>

  return (
    <section className="personal-query">
      <header className="personal-query-heading">
        <div>
          <p className="eyebrow">YOUR ACCOUNT DATA</p>
          <h2>Personal data query builder</h2>
          <p className="muted">Build a query with approved actions. Your account scope is applied automatically.</p>
        </div>
      </header>

      <div className="query-safety" role="note">
        <strong>Private and constrained</strong>
        <span>Only your six account tables are available. Raw SQL is not accepted; changes can only affect your own records.</span>
        <span>Queries return at most 100 rows, use up to 5 filters, and stop after 3 seconds. Notification messages are system-managed.</span>
      </div>
      {error && <p className="error-text" role="alert">{error}</p>}
      {message && <p className="query-success" role="status">{message}</p>}

      {activeTable && (
        <form className="card personal-query-form" onSubmit={run}>
          <div className="query-top-grid">
            <label>Table
              <select value={tableName} onChange={(event) => reset(event.target.value, 'retrieve')}>
                {schema.tables.map((item) => <option value={item.name} key={item.name}>{item.label}</option>)}
              </select>
            </label>
            <label>Action
              <select value={action} onChange={(event) => reset(tableName, event.target.value)}>
                {actions.map((item) => <option value={item} key={item}>{ACTION_LABELS[item]}</option>)}
              </select>
            </label>
            {action === 'retrieve' && <>
              <label>Sort by
                <select value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
                  {activeTable.columns.map((column) => <option value={column.name} key={column.name}>{column.label}</option>)}
                </select>
              </label>
              <label>Order
                <select value={sortDirection} onChange={(event) => setSortDirection(event.target.value)}>
                  <option value="desc">Descending</option><option value="asc">Ascending</option>
                </select>
              </label>
              <label>Maximum rows
                <select value={limit} onChange={(event) => setLimit(event.target.value)}>
                  {[25, 50, 100].map((count) => <option value={count} key={count}>{count}</option>)}
                </select>
              </label>
            </>}
          </div>

          {action === 'retrieve' && <fieldset className="query-columns">
            <legend>Columns to return</legend>
            <div className="query-column-list">
              {activeTable.columns.map((column) => <label className="query-checkbox" key={column.name}>
                <input type="checkbox" checked={columns.includes(column.name)} onChange={(event) => setColumns((current) => event.target.checked ? [...current, column.name] : current.filter((name) => name !== column.name))} />
                {column.label}
              </label>)}
            </div>
          </fieldset>}

          {action === 'retrieve' && <div className="query-filters">
            <div className="query-filter-heading">
              <div><h3>Filters</h3><p className="muted">Combine up to {schema.limits.max_filters} filters.</p></div>
              <div className="query-filter-actions">
                <select aria-label="How filters are combined" value={filterLogic} onChange={(event) => setFilterLogic(event.target.value)}>
                  <option value="and">Match all (AND)</option><option value="or">Match any (OR)</option>
                </select>
                <button type="button" className="ghost" disabled={filters.length >= schema.limits.max_filters} onClick={() => setFilters((current) => [...current, { column: activeTable.columns[0].name, operator: 'eq', value: '' }])}>Add filter</button>
              </div>
            </div>
            {filters.map((filter, index) => {
              const column = activeTable.columns.find((item) => item.name === filter.column) || activeTable.columns[0]
              const ops = FILTER_OPERATORS.filter(([op]) => column.type === 'text'
                ? ['eq', 'neq', 'contains', 'starts_with', 'is_null', 'is_not_null'].includes(op)
                : !['contains', 'starts_with'].includes(op))
              return <div className="query-filter-row" key={`${index}-${filter.column}`}>
                <select aria-label={`Filter ${index + 1} field`} value={filter.column} onChange={(event) => setFilters((current) => current.map((item, i) => i === index ? { column: event.target.value, operator: 'eq', value: '' } : item))}>
                  {activeTable.columns.map((item) => <option value={item.name} key={item.name}>{item.label}</option>)}
                </select>
                <select aria-label={`Filter ${index + 1} operator`} value={filter.operator} onChange={(event) => setFilters((current) => current.map((item, i) => i === index ? { ...item, operator: event.target.value } : item))}>
                  {ops.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                </select>
                {!['is_null', 'is_not_null'].includes(filter.operator) && <input aria-label={`Filter ${index + 1} value`} maxLength={200} value={filter.value} placeholder={column.type === 'timestamp' ? 'ISO time with timezone' : 'Enter a value'} onChange={(event) => setFilters((current) => current.map((item, i) => i === index ? { ...item, value: event.target.value } : item))} />}
                <button type="button" className="danger" onClick={() => setFilters((current) => current.filter((_, i) => i !== index))}>Remove</button>
              </div>
            })}
          </div>}

          {fields.length > 0 && <fieldset className="query-values">
            <legend>{action === 'add' ? 'New record details' : 'Changes to apply'}</legend>
            {fields.map(([key, label, type]) => <label key={key}>
              {label}
              {type === 'boolean' ? <input type="checkbox" checked={Boolean(values[key])} onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.checked }))} /> :
                <ValueInput type={type} value={values[key]} onChange={(value) => setValues((current) => ({ ...current, [key]: value }))} watchlists={watchlists} />}
            </label>)}
          </fieldset>}

          {action === 'modify' && tableName !== 'user_preference' && tableName !== 'app_user' && <div className="query-required-target">
            <h3>Select the record to change</h3>
            <TargetFilter table={activeTable} filters={filters} setFilters={setFilters} watchlists={watchlists} alerts={alerts} notifications={notifications} />
          </div>}
          {action === 'remove' && <div className="query-required-target">
            <h3>Select the record to remove</h3>
            <TargetFilter table={activeTable} filters={filters} setFilters={setFilters} watchlists={watchlists} alerts={alerts} notifications={notifications} />
            <p className="muted">Removal applies only to the selected record in your account.</p>
          </div>}

          <div className="query-submit-row">
            <button className="primary" type="submit" disabled={busy || (action === 'retrieve' && columns.length === 0)}>{busy ? 'Working…' : ACTION_LABELS[action]}</button>
            <span className="muted">The server applies your account scope and validates every field.</span>
          </div>

          <section className="query-sql-preview" aria-labelledby="query-sql-preview-title">
            <div className="query-sql-preview-heading">
              <div>
                <h3 id="query-sql-preview-title">SQL preview</h3>
                <p className="muted">Read-only preview. Values are bound separately by the API and are not included here.</p>
              </div>
              <span className="query-readonly-badge">READ ONLY</span>
            </div>
            <pre aria-label="Read-only SQL query preview"><code>{sqlPreview}</code></pre>
            <p className="muted query-sql-footnote">This preview explains the operation; the server runs its validated, account-scoped query.</p>
          </section>
        </form>
      )}

      {rows && <section className="card query-results">
        <div className="query-filter-heading"><div><h3>{activeTable.label}</h3><p className="muted">Your records only · {rows.length} returned</p></div></div>
        {rows.length === 0 ? <p className="muted">No records match those filters.</p> : <div className="query-table-wrap"><table>
          <thead><tr>{columns.map((column) => <th key={column}>{activeTable.columns.find((item) => item.name === column)?.label || column}</th>)}</tr></thead>
          <tbody>{rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{row[column] == null ? '—' : typeof row[column] === 'object' ? new Date(row[column]).toLocaleString() : String(row[column])}</td>)}</tr>)}</tbody>
        </table></div>}
      </section>}
    </section>
  )
}

function ValueInput({ type, value, onChange, watchlists }) {
  if (type === 'watchlist') return <select required value={value || ''} onChange={(event) => onChange(Number(event.target.value))}>
    <option value="">Choose a watchlist…</option>{watchlists.map((item) => <option value={item.watchlist_no} key={item.watchlist_no}>{item.name}</option>)}
  </select>
  if (type === 'condition') return <select required value={value || 'above'} onChange={(event) => onChange(event.target.value)}><option value="above">Above</option><option value="below">Below</option></select>
  if (type === 'alert_status') return <select required value={value || 'active'} onChange={(event) => onChange(event.target.value)}><option value="active">Active</option><option value="inactive">Inactive</option></select>
  if (type === 'notification_status') return <select required value={value || 'read'} onChange={(event) => onChange(event.target.value)}><option value="read">Read</option><option value="unread">Unread</option></select>
  if (type === 'notification_mode') return <select required value={value || 'in_app'} onChange={(event) => onChange(event.target.value)}><option value="in_app">In app</option><option value="email">Email preference</option></select>
  return <input required type={type} min={type === 'number' ? '0.01' : undefined} step={type === 'number' ? 'any' : undefined} maxLength={type === 'text' || type === 'email' ? 200 : undefined} value={value ?? ''} onChange={(event) => onChange(type === 'number' ? event.target.value : event.target.value)} />
}

function TargetFilter({ table, filters, setFilters, watchlists, alerts, notifications }) {
  const key = table.name === 'watchlist' ? 'watchlist_no'
    : table.name === 'watchlist_security' ? 'watchlist_no'
      : table.name === 'alert' ? 'alert_no'
        : 'notification_id'
  const current = filters.find((item) => item.column === key)?.value || ''
  const setTarget = (column, value) => setFilters((items) => {
    const remaining = items.filter((item) => item.column !== column && !(column === 'watchlist_no' && item.column === 'security_id'))
    if (value === '') return remaining
    return [...remaining, { column, operator: 'eq', value: String(value) }]
  })
  const watchlistNo = Number(current)
  const options = table.name === 'watchlist' || table.name === 'watchlist_security'
    ? watchlists.map((item) => ({ value: item.watchlist_no, label: item.name }))
    : table.name === 'alert'
      ? alerts.map((item) => ({ value: item.alert_no, label: `${item.symbol} · ${item.condition} ${item.target_price}` }))
      : notifications.map((item) => ({ value: item.notification_id, label: `${item.status} · ${item.message}` }))
  const selectedWatchlist = watchlists.find((item) => item.watchlist_no === watchlistNo)
  return <div className="query-target-fields">
    <label>{table.columns.find((item) => item.name === key)?.label || key}
      <select required value={current} onChange={(event) => setTarget(key, event.target.value)}>
        <option value="">Choose a record…</option>
        {options.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}
      </select>
    </label>
    {(table.name === 'watchlist_security') && <label>Security ID
      <select required value={filters.find((item) => item.column === 'security_id')?.value || ''} onChange={(event) => setFilters((items) => [...items.filter((item) => item.column !== 'security_id'), ...(event.target.value ? [{ column: 'security_id', operator: 'eq', value: event.target.value }] : [])])}>
        <option value="">Choose a security…</option>
        {(selectedWatchlist?.stocks || []).map((item) => <option value={item.security_id} key={item.security_id}>{item.symbol}</option>)}
      </select>
    </label>}
  </div>
}
