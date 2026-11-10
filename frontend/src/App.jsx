import { useEffect, useRef, useState } from "react";
import {
  alertsFrom,
  claimHelperFlags,
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
import { becauseLikedText, nextQueueAfterLike, priceLine } from "./cardText";

const USER_KEY = "fund_user_id";

const INTERESTS = [
  { id: "gaming", label: "Gaming" },
  { id: "travel", label: "Travel" },
  { id: "music", label: "Music" },
  { id: "automobile", label: "Automobile" },
];

function newsBlock(card) {
  if (card.news_status === "none") {
    return <p className="row">{card.news_message || "No recent news about this company yet."}</p>;
  }
  if (!card.news_available || !card.latest_news_headline) {
    return <p className="row"><b>Latest news:</b> unavailable</p>;
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
  const updatesFetchId = useRef(0);
  const userIdRef = useRef(userId);
  userIdRef.current = userId;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [finnhub, setFinnhub] = useState("off");
  const [confirmReset, setConfirmReset] = useState(false);
  const [unliking, setUnliking] = useState("");

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
    setError("");
    getCards(userId, 10)
      .then((data) => {
        if (!cancelled) setQueue(data.cards || []);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err.status === 404) {
          forgetUser("That session was not found. Pick your interests again.");
        } else {
          setError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [screen, userId]);

  useEffect(() => {
    if (screen !== "matches" || !userId) return undefined;
    let cancelled = false;
    setLoading(true);
    setError("");
    getMatches(userId)
      .then((data) => {
        if (!cancelled) setMatches(data.matches || []);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err.status === 404) {
          forgetUser("That session was not found. Pick your interests again.");
        } else {
          setError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [screen, userId]);

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
          forgetUser("That session was not found. Pick your interests again.");
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
              forgetUser("That session was not found. Pick your interests again.");
              return;
            }
            setError(err.message);
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
              forgetUser("That session was not found. Pick your interests again.");
              return;
            }
            setError(err.message || "Could not mark alerts as seen.");
          }
        }
      } catch (err) {
        if (!latest()) return;
        if (err.status === 404) {
          forgetUser("That session was not found. Pick your interests again.");
        } else {
          setError(err.message);
        }
      } finally {
        if (!cancelled && latest()) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [screen, userId]);

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
      setError(err.message || "Could not unlike that company.");
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

  return (
    <main>
      <h1>fun(d)</h1>
      <p>Swipe stocks that match what you already care about.</p>

      {userId ? (
        <nav>
          <button type="button" onClick={() => setScreen("swipe")}>Swipe</button>
          <button type="button" onClick={() => setScreen("matches")}>Matches</button>
          <button type="button" onClick={() => setScreen("updates")}>{updatesNavLabel(unseenCount)}</button>
          {confirmReset ? (
            <div>
              <p>Start over? This clears your interests and likes.</p>
              <button type="button" onClick={() => forgetUser("")}>Start over</button>
              <button type="button" onClick={() => setConfirmReset(false)}>Cancel</button>
            </div>
          ) : (
            <button type="button" onClick={() => setConfirmReset(true)}>Start over</button>
          )}
        </nav>
      ) : null}

      {finnhub === "off" && screen !== "onboarding" ? (
        <p className="row">Live price and news are unavailable until a Finnhub key is added.</p>
      ) : null}

      {error ? <p className="error">{error}</p> : null}

      {screen === "onboarding" ? (
        <section>
          <h2>What are you into?</h2>
          <p>Pick one or more. You can change this later with Start over.</p>
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
          <button type="button" onClick={start} disabled={busy}>
            Start
          </button>
        </section>
      ) : null}

      {screen === "swipe" ? (
        <section>
          <h2>Swipe</h2>
          {loading && !current ? <p>Loading a company...</p> : null}
          {!loading && !current ? (
            <p>No more companies for your interests. Open Matches, or start over and pick different interests.</p>
          ) : null}
          {current ? (
            <article className="card">
              {current.logo_url ? (
                <img className="logo" src={current.logo_url} alt="" />
              ) : null}
              <h3>
                {current.company_name} ({current.ticker})
              </h3>
              <Why line={current.why_line} />
              <BecauseLiked card={current} />
              <p className="row">{priceLine(current)}</p>
              <p className="row">{current.short_description}</p>
              {newsBlock(current)}
              <p className="row">{current.quarterly_summary || "Latest quarter: unavailable"}</p>
              <p className="row">{current.quarter_label || "Last quarter: unavailable"}</p>
              <button type="button" onClick={() => swipe("like")} disabled={busy}>
                Like
              </button>
              <button type="button" onClick={() => swipe("dislike")} disabled={busy}>
                Dislike
              </button>
            </article>
          ) : null}
        </section>
      ) : null}

      {screen === "matches" ? (
        <section>
          <h2>Matches</h2>
          {loading ? <p>Loading matches...</p> : null}
          {!loading && matches.length === 0 ? (
            <p>No matches yet. Tap Like on a company you'd like to follow and it'll show up here.</p>
          ) : null}
          {matches.map((match) => (
            <article className="card" key={match.ticker}>
              <h3>
                {match.company_name} ({match.ticker})
              </h3>
              <Why line={match.why_line} />
              <BecauseLiked card={match} />
              <p className="row">{priceLine(match)}</p>
              <p className="row">{match.short_description}</p>
              <button
                type="button"
                onClick={() => unlikeMatch(match.ticker)}
                disabled={unliking === match.ticker}
              >
                Unlike
              </button>
            </article>
          ))}
        </section>
      ) : null}

      {screen === "updates" ? (
        <section>
          <h2>Updates</h2>
          {loading ? <p>Loading updates...</p> : null}
          {!loading ? (
            <UpdatesFeed
              updates={updates}
              alerts={alerts}
              hasLikes={hasLikes}
              digest={digest}
              filings={filings}
              helpers={helpers}
            />
          ) : null}
        </section>
      ) : null}
    </main>
  );
}
