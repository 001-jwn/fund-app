import { useEffect, useRef, useState } from "react";
import {
  alertsFrom,
  claimHelperFlags,
  companyLabel,
  digestSectionFrom,
  unseenCountFrom,
  updatesFrom,
  updatesNavLabel,
} from "./alertView";
import UpdatesFeed from "./UpdatesFeed";
import {
  dislikeCompany,
  getCards,
  getHealth,
  getMatches,
  getUpdates,
  likeCompany,
  markAlertsSeen,
  onboard,
  unlikeCompany,
} from "./api";
import {
  LIVE_DATA_BANNER,
  becauseLikedText,
  nextQueueAfterLike,
  priceLine,
  showLiveDataBanner,
} from "./cardText";

const USER_KEY = "fund_user_id";
const SESSION_MISSING = "We couldn't find your saved picks. Please choose your interests again.";
const LOAD_ERROR = {
  swipe: "Couldn't load companies. Try again.",
  matches: "Couldn't load your matches. Try again.",
  updates: "Couldn't load your updates. Try again.",
};

const INTERESTS = [
  { id: "gaming", label: "Gaming" },
  { id: "travel", label: "Travel" },
  { id: "music", label: "Music" },
  { id: "automobile", label: "Automobile" },
];

function loadErrorMessage(screenName, err) {
  if (err && (err.network || err.specific) && err.message) return err.message;
  return LOAD_ERROR[screenName] || LOAD_ERROR.updates;
}

function NewsBlock({ card }) {
  if (card.news_status === "none") {
    return <p className="row">{card.news_message || "No recent news about this company yet."}</p>;
  }
  if (!card.news_available || !card.latest_news_headline) {
    return <p className="row"><b>Latest news:</b> not available</p>;
  }
  return (
    <div className="row">
      <p><b>Latest news:</b> {card.latest_news_headline}</p>
      {card.latest_news_summary ? <p>{card.latest_news_summary}</p> : null}
      {card.news_date_label ? <p>{card.news_date_label}</p> : null}
    </div>
  );
}

function Why({ line }) {
  return (
    <div className="why">
      <div className="why-label">Why you're seeing this</div>
      <p>{line}</p>
    </div>
  );
}

function BecauseLiked({ card }) {
  const text = becauseLikedText(card);
  if (!text) return null;
  return <p className="row">{text}</p>;
}

function Logo({ ticker, url }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setFailed(false);
  }, [url]);
  const letter = (typeof ticker === "string" && ticker.trim().charAt(0).toUpperCase()) || "?";
  if (!url || failed) {
    return <span className="logo-fallback" aria-hidden="true">{letter}</span>;
  }
  return <img className="logo" src={url} alt="" onError={() => setFailed(true)} />;
}

export function CompanyCard({ card, showNews, children }) {
  const price = priceLine(card);
  return (
    <article className="card">
      <Logo ticker={card.ticker} url={card.logo_url} />
      <h3>{companyLabel(card)}</h3>
      <Why line={card.why_line} />
      <BecauseLiked card={card} />
      {price ? <p className="row">{price}</p> : null}
      <p className="row">{card.short_description}</p>
      {showNews ? <NewsBlock card={card} /> : null}
      {showNews ? (
        <p className="row">{card.quarterly_summary || "Latest quarter: not available"}</p>
      ) : null}
      {showNews ? (
        <p className="row">{card.quarter_label || "Last quarter: not available"}</p>
      ) : null}
      {children}
    </article>
  );
}

export default function App() {
  const [screen, setScreen] = useState(() =>
    localStorage.getItem(USER_KEY) ? "swipe" : "onboarding"
  );
  const [userId, setUserId] = useState(() => localStorage.getItem(USER_KEY) || "");
  const [picked, setPicked] = useState([]);
  const [queue, setQueue] = useState([]);
  const [matches, setMatches] = useState([]);
  const [updates, setUpdates] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [digest, setDigest] = useState(null);
  const [filings, setFilings] = useState(null);
  const [unseenCount, setUnseenCount] = useState(0);
  const [hasLikes, setHasLikes] = useState(null);
  const [helpers, setHelpers] = useState({ price: false, earnings: false });
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [loadErrorScreen, setLoadErrorScreen] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const updatesFetchId = useRef(0);
  const userIdRef = useRef(userId);
  userIdRef.current = userId;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [finnhub, setFinnhub] = useState("off");
  const [confirmReset, setConfirmReset] = useState(false);
  const [unliking, setUnliking] = useState("");

  function retryLoad() {
    setLoadError("");
    setLoadErrorScreen("");
    setError("");
    setReloadKey((value) => value + 1);
  }

  function failLoad(which, err) {
    setLoadError(loadErrorMessage(which, err));
    setLoadErrorScreen(which);
  }

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((health) => {
        if (!cancelled) setFinnhub(health.finnhub || "off");
      })
      .catch(() => {
        if (!cancelled) setFinnhub("off");
      });
    return () => {
      cancelled = true;
    };
  }, [screen]);

  useEffect(() => {
    if (screen !== "swipe" || !userId) return undefined;
    let cancelled = false;
    setLoading(true);
    setLoadError("");
    setLoadErrorScreen("");
    setError("");
    getCards(userId, 10)
      .then((data) => {
        if (!cancelled) setQueue(data.cards || []);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err.status === 404) {
          forgetUser(SESSION_MISSING);
        } else {
          failLoad("swipe", err);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [screen, userId, reloadKey]);

  useEffect(() => {
    if (screen !== "matches" || !userId) return undefined;
    let cancelled = false;
    setLoading(true);
    setLoadError("");
    setLoadErrorScreen("");
    setError("");
    getMatches(userId)
      .then((data) => {
        if (!cancelled) setMatches(data.matches || []);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err.status === 404) {
          forgetUser(SESSION_MISSING);
        } else {
          failLoad("matches", err);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [screen, userId, reloadKey]);

  useEffect(() => {
    if (!userId) return undefined;
    const fetchId = ++updatesFetchId.current;
    let cancelled = false;
    getUpdates(userId)
      .then((data) => {
        if (cancelled || fetchId !== updatesFetchId.current || userIdRef.current !== userId) return;
        setUnseenCount(unseenCountFrom(data));
      })
      .catch((err) => {
        if (cancelled || fetchId !== updatesFetchId.current || userIdRef.current !== userId) return;
        if (err.status === 404) {
          forgetUser(SESSION_MISSING);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [userId]);

  useEffect(() => {
    if (screen !== "updates" || !userId) return undefined;
    const fetchId = ++updatesFetchId.current;
    let cancelled = false;
    const latest = () => fetchId === updatesFetchId.current && userIdRef.current === userId;
    setLoading(true);
    setLoadError("");
    setLoadErrorScreen("");
    setError("");
    (async () => {
      try {
        const data = await getUpdates(userId);
        if (!latest()) return;
        const nextUpdates = updatesFrom(data);
        const nextAlerts = alertsFrom(data);
        const unseen = unseenCountFrom(data);
        let likes = nextUpdates.length > 0 || nextAlerts.length > 0 ? true : null;
        if (likes === null && digestSectionFrom(data, true)) likes = true;
        if (likes === null) {
          try {
            const matchData = await getMatches(userId);
            if (!latest()) return;
            likes = Array.isArray(matchData.matches) && matchData.matches.length > 0;
          } catch (err) {
            if (!latest()) return;
            if (err.status === 404) {
              forgetUser(SESSION_MISSING);
              return;
            }
            failLoad("updates", err);
            return;
          }
        }
        let nextHelpers = { price: false, earnings: false };
        if (!cancelled) {
          nextHelpers = await claimHelperFlags(userId, nextAlerts, localStorage);
        }
        if (!latest()) return;
        setUpdates(nextUpdates);
        setAlerts(nextAlerts);
        setDigest(digestSectionFrom(data, likes));
        setFilings(data ? data.filings : null);
        setHasLikes(likes);
        setHelpers(nextHelpers);
        setUnseenCount(unseen);
        if (unseen > 0 && !cancelled) {
          try {
            const seen = await markAlertsSeen(userId);
            if (!latest()) return;
            setUnseenCount(unseenCountFrom(seen));
          } catch (err) {
            if (!latest()) return;
            if (err.status === 404) {
              forgetUser(SESSION_MISSING);
              return;
            }
            setError(err.message || "Couldn't update your alerts. Try again.");
          }
        }
      } catch (err) {
        if (!latest()) return;
        if (err.status === 404) {
          forgetUser(SESSION_MISSING);
        } else {
          failLoad("updates", err);
        }
      } finally {
        if (!cancelled && latest()) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [screen, userId, reloadKey]);

  const current = queue[0];

  useEffect(() => {
    if (screen !== "swipe" || !userId || finnhub !== "on" || !current) return undefined;
    const newsSettled = current.news_available || current.news_status === "none";
    if (current.price_available && newsSettled && current.logo_url) return undefined;
    const ticker = current.ticker;
    const timer = setInterval(() => {
      getCards(userId, 10)
        .then((data) => {
          const fresh = (data.cards || []).find((card) => card.ticker === ticker);
          if (!fresh) return;
          setQueue((prev) => prev.map((card) => (card.ticker === ticker ? fresh : card)));
        })
        .catch(() => {});
    }, 8000);
    return () => clearInterval(timer);
  }, [screen, userId, finnhub, current]);

  function forgetUser(message) {
    localStorage.removeItem(USER_KEY);
    setUserId("");
    setQueue([]);
    setMatches([]);
    setUpdates([]);
    setAlerts([]);
    setDigest(null);
    setFilings(null);
    setUnseenCount(0);
    setHasLikes(null);
    setHelpers({ price: false, earnings: false });
    setLoading(false);
    setLoadError("");
    setLoadErrorScreen("");
    setPicked([]);
    setConfirmReset(false);
    setScreen("onboarding");
    setError(message || "");
  }

  async function unlikeMatch(ticker) {
    if (!ticker || unliking) return;
    setUnliking(ticker);
    setError("");
    try {
      await unlikeCompany(userId, ticker);
      setMatches((prev) => prev.filter((match) => match.ticker !== ticker));
    } catch (err) {
      setError(err.message || "Couldn't remove that company. Try again.");
    } finally {
      setUnliking("");
    }
  }

  function toggleInterest(id) {
    setPicked((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));
  }

  async function start() {
    if (picked.length === 0) {
      setError("Pick at least one interest.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await onboard(picked);
      localStorage.setItem(USER_KEY, result.user_id);
      setAlerts([]);
      setDigest(null);
      setFilings(null);
      setUnseenCount(0);
      setHasLikes(null);
      setHelpers({ price: false, earnings: false });
      setUserId(result.user_id);
      setQueue([]);
      setScreen("swipe");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function swipe(action) {
    if (!current || busy) return;
    const queueNow = queue;
    const ticker = current.ticker;
    setBusy(true);
    setError("");
    try {
      if (action === "like") {
        await likeCompany(userId, ticker);
        try {
          const data = await getCards(userId, 10);
          setQueue(nextQueueAfterLike(queueNow, ticker, data.cards));
        } catch (err) {
          setQueue(queueNow.filter((card) => card.ticker !== ticker));
          throw err;
        }
      } else {
        await dislikeCompany(userId, ticker);
        const rest = queueNow.slice(1);
        if (rest.length < 3) {
          const data = await getCards(userId, 10);
          const seen = new Set(rest.map((card) => card.ticker));
          const extra = (data.cards || []).filter((card) => !seen.has(card.ticker));
          setQueue(rest.concat(extra));
        } else {
          setQueue(rest);
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const showBanner = showLiveDataBanner({ screen, card: current, matches });
  const screenLoadError = loadErrorScreen === screen ? loadError : "";

  return (
    <main>
      <h1>fun(d)</h1>
      <p className="tagline">better information, simply</p>
      <p className="subtitle">Swipe stocks that match what you already care about.</p>

      {userId ? (
        <nav>
          <button
            type="button"
            className={screen === "swipe" ? "active" : ""}
            onClick={() => setScreen("swipe")}
          >
            Swipe
          </button>
          <button
            type="button"
            className={screen === "matches" ? "active" : ""}
            onClick={() => setScreen("matches")}
          >
            Matches
          </button>
          <button
            type="button"
            className={screen === "updates" ? "active" : ""}
            onClick={() => setScreen("updates")}
          >
            {updatesNavLabel(unseenCount)}
          </button>
          <button type="button" onClick={() => setConfirmReset(true)}>Start over</button>
        </nav>
      ) : null}

      {confirmReset ? (
        <div className="confirm">
          <p>Start over? This clears your interests and likes.</p>
          <div className="actions">
            <button type="button" className="primary" onClick={() => forgetUser("")}>Start over</button>
            <button type="button" onClick={() => setConfirmReset(false)}>Cancel</button>
          </div>
        </div>
      ) : null}

      {showBanner ? <p className="banner">{LIVE_DATA_BANNER}</p> : null}

      {error ? <p className="error">{error}</p> : null}

      {screen === "onboarding" ? (
        <section>
          <h2>What are you into?</h2>
          <p>Pick one or more. You can change this later by starting over.</p>
          {INTERESTS.map((interest) => (
            <label key={interest.id}>
              <input
                type="checkbox"
                checked={picked.includes(interest.id)}
                onChange={() => toggleInterest(interest.id)}
              />{" "}
              {interest.label}
            </label>
          ))}
          <button type="button" className="primary" onClick={start} disabled={busy}>
            Start
          </button>
        </section>
      ) : null}

      {screen === "swipe" ? (
        <section>
          <h2>Swipe</h2>
          {loading && !current ? <p>Loading companies...</p> : null}
          {!loading && screenLoadError ? (
            <div className="state">
              <p>{screenLoadError}</p>
              <button type="button" className="primary" onClick={retryLoad}>Try again</button>
            </div>
          ) : null}
          {!loading && !screenLoadError && !current ? (
            <div className="state">
              <p>No more companies right now for the interests you picked. Open Matches, or start over to pick different ones.</p>
              <div className="actions">
                <button type="button" className="primary" onClick={() => setScreen("matches")}>Open Matches</button>
                <button type="button" onClick={() => setConfirmReset(true)}>Start over</button>
              </div>
            </div>
          ) : null}
          {current && !screenLoadError ? (
            <CompanyCard card={current} showNews>
              <div className="actions">
                <button type="button" className="primary" onClick={() => swipe("like")} disabled={busy}>
                  Like
                </button>
                <button type="button" onClick={() => swipe("dislike")} disabled={busy}>
                  Pass
                </button>
              </div>
            </CompanyCard>
          ) : null}
        </section>
      ) : null}

      {screen === "matches" ? (
        <section>
          <h2>Matches</h2>
          {loading ? <p>Loading matches...</p> : null}
          {!loading && screenLoadError ? (
            <div className="state">
              <p>{screenLoadError}</p>
              <button type="button" className="primary" onClick={retryLoad}>Try again</button>
            </div>
          ) : null}
          {!loading && !screenLoadError && matches.length === 0 ? (
            <div className="state">
              <p>No matches yet. Swipe right or press Like to save a company here.</p>
              <button type="button" className="primary" onClick={() => setScreen("swipe")}>Start swiping</button>
            </div>
          ) : null}
          {!screenLoadError ? matches.map((match) => (
            <CompanyCard card={match} showNews={false} key={match.ticker}>
              <button
                type="button"
                onClick={() => unlikeMatch(match.ticker)}
                disabled={unliking === match.ticker}
              >
                Remove
              </button>
            </CompanyCard>
          )) : null}
        </section>
      ) : null}

      {screen === "updates" ? (
        <section>
          <h2>Updates</h2>
          {loading ? <p>Loading updates...</p> : null}
          {!loading && screenLoadError ? (
            <div className="state">
              <p>{screenLoadError}</p>
              <button type="button" className="primary" onClick={retryLoad}>Try again</button>
            </div>
          ) : null}
          {!loading && !screenLoadError ? (
            <UpdatesFeed
              updates={updates}
              alerts={alerts}
              hasLikes={hasLikes}
              digest={digest}
              filings={filings}
              helpers={helpers}
              emptyAction={{ label: "Start swiping", onClick: () => setScreen("swipe") }}
            />
          ) : null}
        </section>
      ) : null}
    </main>
  );
}
