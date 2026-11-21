import {
  FILING_LINK_LABEL,
  alertKindLabel,
  companyHeading,
  filingHelpers,
  helperForAlert,
  newsAlertUrl,
  updatesFeed,
} from "./alertView";

function AlertCard({ alert, helper }) {
  const url = newsAlertUrl(alert);
  const line = typeof alert.line === "string" ? alert.line : "";
  const unseen = alert.seen !== true;
  const heading = companyHeading(alert);
  return (
    <article className="card alert">
      <p className="alert-label">
        Alert · {alertKindLabel(alert.kind)}
        {unseen ? " · New" : ""}
      </p>
      {heading ? <p className="row">{heading}</p> : null}
      {url ? (
        <p className={unseen ? "row unseen" : "row"}>
          <a href={url} target="_blank" rel="noopener noreferrer">{line}</a>
        </p>
      ) : (
        <p className={unseen ? "row unseen" : "row"}>{line}</p>
      )}
      {helper ? <p className="helper">{helper}</p> : null}
    </article>
  );
}

function DailyCard({ update }) {
  const lines = Array.isArray(update.lines) ? update.lines : [];
  const newsUrl = typeof update.news_url === "string" && update.news_url ? update.news_url : null;
  const heading = companyHeading(update);
  return (
    <article className="card">
      {heading ? <h3>{heading}</h3> : null}
      {lines.map((line, index) => {
        const linked = Boolean(newsUrl) && index === lines.length - 1;
        if (linked) {
          return (
            <p className="row" key={`${update.ticker}-${index}`}>
              <a href={newsUrl} target="_blank" rel="noopener noreferrer">{line}</a>
            </p>
          );
        }
        return (
          <p className="row" key={`${update.ticker}-${index}`}>{line}</p>
        );
      })}
    </article>
  );
}

function FilingCard({ filing, outlook }) {
  return (
    <article className="card">
      {filing.name ? <h3>{filing.name}</h3> : null}
      <p className="row">{filing.line}</p>
      {filing.url ? (
        <p className="row">
          <a href={filing.url} target="_blank" rel="noopener noreferrer">{FILING_LINK_LABEL}</a>
        </p>
      ) : null}
      {outlook ? <p className="helper">{outlook}</p> : null}
    </article>
  );
}

export default function UpdatesFeed({ updates, alerts, hasLikes, digest, filings, helpers, emptyAction }) {
  const feed = updatesFeed({ updates, alerts, hasLikes, digest, filings });
  const filingNotes = filingHelpers(feed.filings);
  return (
    <div>
      {feed.digest.map((block, index) =>
        block.role === "header" ? (
          <h3 key={`digest-${index}`}>{block.text}</h3>
        ) : (
          <p className="row" key={`digest-${index}`}>{block.text}</p>
        )
      )}
      {feed.alerts.length > 0 ? (
        <div>
          <h3>Alerts</h3>
          {feed.alerts.map((alert, index) => (
            <AlertCard
              key={`${alert.id ?? "alert"}-${index}`}
              alert={alert}
              helper={helperForAlert(alert, feed.alerts, helpers)}
            />
          ))}
        </div>
      ) : null}
      {feed.emptyText ? (
        <div className="state">
          <p>{feed.emptyText}</p>
          {emptyAction ? (
            <button type="button" className="primary" onClick={emptyAction.onClick}>
              {emptyAction.label}
            </button>
          ) : null}
        </div>
      ) : null}
      {feed.filings.length > 0 ? (
        <div>
          <h3>SEC filings</h3>
          {filingNotes.sec ? <p className="helper">{filingNotes.sec}</p> : null}
          {feed.filings.map((filing, index) => (
            <FilingCard
              key={`filing-${index}`}
              filing={filing}
              outlook={index === filingNotes.outlookIndex ? filingNotes.outlook : ""}
            />
          ))}
        </div>
      ) : null}
      {feed.daily.length > 0 ? (
        <div>
          <h3>Daily updates</h3>
          {feed.daily.map((update) => (
            <DailyCard key={update.ticker} update={update} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
