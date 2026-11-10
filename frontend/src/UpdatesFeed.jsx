import {
  FILING_LINK_LABEL,
  alertKindLabel,
  filingHelpers,
  helperForAlert,
  newsAlertUrl,
  updatesFeed,
} from "./alertView";

function AlertCard({ alert, helper }) {
  const url = newsAlertUrl(alert);
  const line = typeof alert.line === "string" ? alert.line : "";
  const unseen = alert.seen !== true;
  return (
    <article className="card alert">
      <p className="alert-label">
        Alert · {alertKindLabel(alert.kind)}
        {unseen ? " · New" : ""}
      </p>
      <p className="row">{alert.ticker}</p>
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
  return (
    <article className="card">
      <h3>{update.ticker}</h3>
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
      {filing.name ? <p className="row">{filing.name}</p> : null}
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

export default function UpdatesFeed({ updates, alerts, hasLikes, digest, filings, helpers }) {
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
      {feed.emptyText ? <p>{feed.emptyText}</p> : null}
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
