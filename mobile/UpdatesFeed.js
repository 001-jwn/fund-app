import { Linking, Pressable, Text, View } from "react-native";
import {
  FILING_LINK_LABEL,
  alertKindLabel,
  filingHelpers,
  helperForAlert,
  newsAlertUrl,
  updatesFeed,
} from "./alertView";

function AlertCard({ alert, helper, onLinkError, styles }) {
  const url = newsAlertUrl(alert);
  const line = typeof alert.line === "string" ? alert.line : "";
  const unseen = alert.seen !== true;
  const lineStyle = [styles.row, unseen ? styles.unseen : null, url ? styles.link : null];
  return (
    <View style={styles.alertCard}>
      <Text style={styles.alertLabel}>
        Alert · {alertKindLabel(alert.kind)}
        {unseen ? " · New" : ""}
      </Text>
      <Text style={styles.row}>{alert.ticker}</Text>
      {url ? (
        <Pressable
          onPress={() => {
            Linking.openURL(url).catch(() => {
              onLinkError("Could not open that link.");
            });
          }}
        >
          <Text style={lineStyle}>{line}</Text>
        </Pressable>
      ) : (
        <Text style={lineStyle}>{line}</Text>
      )}
      {helper ? <Text style={styles.helper}>{helper}</Text> : null}
    </View>
  );
}

function DailyCard({ update, onLinkError, styles }) {
  const lines = Array.isArray(update.lines) ? update.lines : [];
  const newsUrl = typeof update.news_url === "string" && update.news_url ? update.news_url : null;
  return (
    <View style={styles.card}>
      <Text style={styles.company}>{update.ticker}</Text>
      {lines.map((line, index) => {
        const linked = Boolean(newsUrl) && index === lines.length - 1;
        if (linked) {
          return (
            <Pressable
              key={`${update.ticker}-${index}`}
              onPress={() => {
                Linking.openURL(newsUrl).catch(() => {
                  onLinkError("Could not open that link.");
                });
              }}
            >
              <Text style={[styles.row, styles.link]}>{line}</Text>
            </Pressable>
          );
        }
        return (
          <Text style={styles.row} key={`${update.ticker}-${index}`}>{line}</Text>
        );
      })}
    </View>
  );
}

function FilingCard({ filing, outlook, onLinkError, styles }) {
  return (
    <View style={styles.card}>
      {filing.name ? <Text style={styles.company}>{filing.name}</Text> : null}
      <Text style={styles.row}>{filing.line}</Text>
      {filing.url ? (
        <Pressable
          onPress={() => {
            Linking.openURL(filing.url).catch(() => {
              onLinkError("Could not open that link.");
            });
          }}
        >
          <Text style={[styles.row, styles.link]}>{FILING_LINK_LABEL}</Text>
        </Pressable>
      ) : null}
      {outlook ? <Text style={styles.helper}>{outlook}</Text> : null}
    </View>
  );
}

export default function UpdatesFeed({
  updates,
  alerts,
  hasLikes,
  digest,
  filings,
  helpers,
  styles,
  onLinkError,
}) {
  const feed = updatesFeed({ updates, alerts, hasLikes, digest, filings });
  const filingNotes = filingHelpers(feed.filings);
  return (
    <View>
      {feed.digest.map((block, index) =>
        block.role === "header" ? (
          <Text key={`digest-${index}`} style={styles.sectionLabel}>{block.text}</Text>
        ) : (
          <Text key={`digest-${index}`} style={styles.row}>{block.text}</Text>
        )
      )}
      {feed.alerts.length > 0 ? (
        <View>
          <Text style={styles.sectionLabel}>Alerts</Text>
          {feed.alerts.map((alert, index) => (
            <AlertCard
              key={`${alert.id ?? "alert"}-${index}`}
              alert={alert}
              helper={helperForAlert(alert, feed.alerts, helpers)}
              onLinkError={onLinkError}
              styles={styles}
            />
          ))}
        </View>
      ) : null}
      {feed.emptyText ? <Text style={styles.row}>{feed.emptyText}</Text> : null}
      {feed.filings.length > 0 ? (
        <View>
          <Text style={styles.sectionLabel}>SEC filings</Text>
          {filingNotes.sec ? <Text style={styles.helper}>{filingNotes.sec}</Text> : null}
          {feed.filings.map((filing, index) => (
            <FilingCard
              key={`filing-${index}`}
              filing={filing}
              outlook={index === filingNotes.outlookIndex ? filingNotes.outlook : ""}
              onLinkError={onLinkError}
              styles={styles}
            />
          ))}
        </View>
      ) : null}
      {feed.daily.length > 0 ? (
        <View>
          <Text style={styles.sectionLabel}>Daily updates</Text>
          {feed.daily.map((update) => (
            <DailyCard
              key={update.ticker}
              update={update}
              onLinkError={onLinkError}
              styles={styles}
            />
          ))}
        </View>
      ) : null}
    </View>
  );
}
