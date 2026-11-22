import { useEffect, useRef, useState } from "react";
import { StatusBar } from "expo-status-bar";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import {
  Alert,
  Animated,
  Dimensions,
  Image,
  PanResponder,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
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
import { SWIPE_DISTANCE_FRACTION, swipeDecision } from "./swipeDecision";

const USER_KEY = "fund_user_id";
const SESSION_MISSING = "We couldn't find your saved picks. Please choose your interests again.";
const LOAD_ERROR = {
  swipe: "Couldn't load companies. Try again.",
  matches: "Couldn't load your matches. Try again.",
  updates: "Couldn't load your updates. Try again.",
};

const ACCENT = "#0b6e56";
const INK = "#1c1c1c";
const PAPER = "#f6f5f2";
const LINE = "#e3e0d8";
const TYPE = { title: 22, body: 16, caption: 13 };
const SPACE = { sm: 8, md: 16 };

function loadErrorMessage(screenName, err) {
  if (err && (err.network || err.specific) && err.message) return err.message;
  return LOAD_ERROR[screenName] || LOAD_ERROR.updates;
}

const INTERESTS = [
  { id: "gaming", label: "Gaming" },
  { id: "travel", label: "Travel" },
  { id: "music", label: "Music" },
  { id: "automobile", label: "Automobile" },
];

function NewsBlock({ card }) {
  if (card.news_status === "none") {
    return (
      <Text style={styles.row}>
        {card.news_message || "No recent news about this company yet."}
      </Text>
    );
  }
  if (!card.news_available || !card.latest_news_headline) {
    return (
      <Text style={styles.row}>
        <Text style={styles.bold}>Latest news:</Text> not available
      </Text>
    );
  }
  return (
    <View style={styles.row}>
      <Text>
        <Text style={styles.bold}>Latest news:</Text> {card.latest_news_headline}
      </Text>
      {card.latest_news_summary ? <Text>{card.latest_news_summary}</Text> : null}
      {card.news_date_label ? <Text>{card.news_date_label}</Text> : null}
    </View>
  );
}

function Why({ line }) {
  return (
    <View style={styles.why}>
      <Text style={styles.whyLabel}>Why you're seeing this</Text>
      <Text>{line}</Text>
    </View>
  );
}

function BecauseLiked({ card }) {
  const text = becauseLikedText(card);
  if (!text) return null;
  return <Text style={styles.row}>{text}</Text>;
}

function Logo({ ticker, url }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setFailed(false);
  }, [url]);
  const letter = (typeof ticker === "string" && ticker.trim().charAt(0).toUpperCase()) || "?";
  if (!url || failed) {
    return (
      <View style={styles.logoFallback}>
        <Text style={styles.logoLetter}>{letter}</Text>
      </View>
    );
  }
  return (
    <Image
      source={{ uri: url }}
      style={styles.logo}
      resizeMode="contain"
      onError={() => setFailed(true)}
    />
  );
}

function CompanyFacts({ card, showNews }) {
  // holder_count is omitted by the API and stays off the card, same as the website.
  const price = priceLine(card);
  return (
    <View>
      <Logo ticker={card.ticker} url={card.logo_url} />
      <Text style={styles.company}>{companyLabel(card)}</Text>
      <Why line={card.why_line} />
      <BecauseLiked card={card} />
      {price ? <Text style={styles.row}>{price}</Text> : null}
      <Text style={styles.row}>{card.short_description}</Text>
      {showNews ? <NewsBlock card={card} /> : null}
      {showNews ? (
        <Text style={styles.row}>{card.quarterly_summary || "Latest quarter: not available"}</Text>
      ) : null}
      {showNews ? (
        <Text style={styles.row}>{card.quarter_label || "Last quarter: not available"}</Text>
      ) : null}
    </View>
  );
}

function SwipeableCard({ busy, onSwipe, onSwipeStart, onSwipeEnd, children }) {
  const pan = useRef(new Animated.ValueXY()).current;
  const onSwipeRef = useRef(onSwipe);
  const onSwipeStartRef = useRef(onSwipeStart);
  const onSwipeEndRef = useRef(onSwipeEnd);
  const busyRef = useRef(busy);
  const locked = useRef(false);
  const cardWidth = useRef(0);
  const [measuredWidth, setMeasuredWidth] = useState(0);
  const scrollHeld = useRef(false);
  const granted = useRef(false);
  onSwipeRef.current = onSwipe;
  onSwipeStartRef.current = onSwipeStart;
  onSwipeEndRef.current = onSwipeEnd;
  busyRef.current = busy;

  function holdScroll() {
    if (scrollHeld.current) return;
    scrollHeld.current = true;
    onSwipeStartRef.current?.();
  }

  function releaseScroll() {
    if (!scrollHeld.current) return;
    scrollHeld.current = false;
    onSwipeEndRef.current?.();
  }

  useEffect(() => {
    return () => {
      if (!scrollHeld.current) return;
      scrollHeld.current = false;
      onSwipeEndRef.current?.();
    };
  }, []);

  function springBack() {
    Animated.spring(pan, {
      toValue: { x: 0, y: 0 },
      useNativeDriver: false,
    }).start();
  }

  function settle(gesture) {
    granted.current = false;
    releaseScroll();
    if (locked.current) return;
    const width = cardWidth.current > 0 ? cardWidth.current : Dimensions.get("window").width;
    // Claim already required |dx| > |dy|. A finger that drifts vertical after
    // that still commits when the distance or flick test passes.
    const action = swipeDecision(gesture.dx, gesture.vx, width);
    let toX = 0;
    if (action === "like") toX = 500;
    else if (action === "dislike") toX = -500;
    if (!action || busyRef.current) {
      springBack();
      return;
    }
    locked.current = true;
    Animated.timing(pan, {
      toValue: { x: toX, y: 0 },
      duration: 160,
      useNativeDriver: false,
    }).start(() => {
      Promise.resolve(onSwipeRef.current(action)).finally(() => {
        locked.current = false;
        pan.setValue({ x: 0, y: 0 });
      });
    });
  }

  const responder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponderCapture: (_, gesture) => {
        if (busyRef.current || locked.current) {
          releaseScroll();
          return false;
        }
        const horizontal = Math.abs(gesture.dx) > 12 && Math.abs(gesture.dx) > Math.abs(gesture.dy);
        if (horizontal) holdScroll();
        else if (!granted.current) releaseScroll();
        return horizontal;
      },
      onPanResponderGrant: () => {
        granted.current = true;
        holdScroll();
      },
      onPanResponderReject: () => {
        granted.current = false;
        releaseScroll();
      },
      // The card sits in a ScrollView. Once a horizontal swipe has started,
      // keep the responder. scrollEnabled is also turned off until this gesture ends.
      onPanResponderTerminationRequest: () => false,
      onPanResponderMove: (_, gesture) => {
        if (busyRef.current || locked.current) {
          releaseScroll();
          return;
        }
        pan.setValue({ x: gesture.dx, y: gesture.dy * 0.2 });
      },
      onPanResponderRelease: (_, gesture) => {
        settle(gesture);
      },
      onPanResponderTerminate: (_, gesture) => {
        settle(gesture);
      },
    })
  ).current;

  const layoutWidth = measuredWidth > 0 ? measuredWidth : Dimensions.get("window").width;
  const swipeLine = layoutWidth * SWIPE_DISTANCE_FRACTION;
  // ±10 degrees when the finger reaches the commit line (25% of the card).
  const tilt = pan.x.interpolate({
    inputRange: [-swipeLine, 0, swipeLine],
    outputRange: ["-10deg", "0deg", "10deg"],
    extrapolate: "clamp",
  });

  return (
    <Animated.View
      onLayout={(event) => {
        const next = event.nativeEvent.layout.width;
        cardWidth.current = next;
        setMeasuredWidth((prev) => (prev === next ? prev : next));
      }}
      style={{
        transform: [
          { translateX: pan.x },
          { translateY: pan.y },
          { rotate: tilt },
        ],
      }}
      {...responder.panHandlers}
    >
      {children}
    </Animated.View>
  );
}

export default function App() {
  const [ready, setReady] = useState(false);
  const [screen, setScreen] = useState("onboarding");
  const [userId, setUserId] = useState("");
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
  const [scrollEnabled, setScrollEnabled] = useState(true);
  const scrollRef = useRef(null);
  const [error, setError] = useState("");
  const [finnhub, setFinnhub] = useState("off");
  const [unliking, setUnliking] = useState("");
  const swipeLock = useRef(false);

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

  function setSwipeScrollEnabled(enabled) {
    const view = scrollRef.current;
    if (view != null && typeof view.setNativeProps === "function") {
      view.setNativeProps({ scrollEnabled: enabled });
    } else {
      // This ScrollView class keeps setNativeProps on the native node.
      const native = view?.getNativeScrollRef?.() ?? null;
      native?.setNativeProps?.({ scrollEnabled: enabled });
    }
    setScrollEnabled(enabled);
  }

  useEffect(() => {
    let cancelled = false;
    AsyncStorage.getItem(USER_KEY)
      .then((stored) => {
        if (cancelled || !stored) return;
        setUserId(stored);
        setScreen("swipe");
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || "Couldn't load your saved picks. You can start again.");
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!ready) return undefined;
    let cancelled = false;
    getHealth()
      .then((health) => {
        if (!cancelled) setFinnhub(health.finnhub || "off");
      })
      .catch((err) => {
        if (cancelled) return;
        setFinnhub("off");
        if (!process.env.EXPO_PUBLIC_API_URL) {
          setError(err.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [ready, screen]);

  useEffect(() => {
    if (!ready || screen !== "swipe" || !userId) return undefined;
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
  }, [ready, screen, userId, reloadKey]);

  useEffect(() => {
    if (!ready || screen !== "matches" || !userId) return undefined;
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
  }, [ready, screen, userId, reloadKey]);

  useEffect(() => {
    if (!ready || !userId) return undefined;
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
  }, [ready, userId]);

  useEffect(() => {
    if (!ready || screen !== "updates" || !userId) return undefined;
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
          nextHelpers = await claimHelperFlags(userId, nextAlerts, AsyncStorage);
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
  }, [ready, screen, userId, reloadKey]);

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

  async function forgetUser(message) {
    await AsyncStorage.removeItem(USER_KEY);
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
      await AsyncStorage.setItem(USER_KEY, result.user_id);
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
    if (!current || busy || swipeLock.current) return;
    swipeLock.current = true;
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
      setSwipeScrollEnabled(true);
      setError(err.message);
    } finally {
      swipeLock.current = false;
      setBusy(false);
    }
  }

  function askReset() {
    Alert.alert("Start over?", "This clears your interests and likes.", [
      { text: "Cancel", style: "cancel" },
      { text: "Start over", onPress: () => forgetUser("") },
    ]);
  }

  const showBanner = showLiveDataBanner({ screen, card: current, matches });
  const screenLoadError = loadErrorScreen === screen ? loadError : "";

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.screen} edges={["top", "bottom", "left", "right"]}>
        <StatusBar style="dark" />
        <ScrollView
          ref={scrollRef}
          scrollEnabled={scrollEnabled}
          contentContainerStyle={styles.content}
        >
          <Text style={styles.title}>fun(d)</Text>
          <Text style={styles.tagline}>better information, simply</Text>
          <Text style={styles.body}>Swipe stocks that match what you already care about.</Text>

          {ready && userId ? (
            <View style={styles.nav}>
              <NavButton label="Swipe" selected={screen === "swipe"} onPress={() => setScreen("swipe")} />
              <NavButton label="Matches" selected={screen === "matches"} onPress={() => setScreen("matches")} />
              <NavButton
                label={updatesNavLabel(unseenCount)}
                selected={screen === "updates"}
                onPress={() => setScreen("updates")}
              />
              <NavButton label="Start over" onPress={askReset} />
            </View>
          ) : null}

          {showBanner ? <Text style={styles.banner}>{LIVE_DATA_BANNER}</Text> : null}

          {error ? <Text style={styles.error}>{error}</Text> : null}

          {ready && screen === "onboarding" ? (
            <View>
              <Text style={styles.heading}>What are you into?</Text>
              <Text style={styles.body}>Pick one or more. You can change this later by starting over.</Text>
              {INTERESTS.map((interest) => {
                const selected = picked.includes(interest.id);
                return (
                  <Pressable
                    key={interest.id}
                    onPress={() => toggleInterest(interest.id)}
                    accessibilityRole="checkbox"
                    accessibilityState={{ checked: selected }}
                  >
                    <Text style={styles.choice}>
                      {selected ? "[x]" : "[ ]"} {interest.label}
                    </Text>
                  </Pressable>
                );
              })}
              <Action label="Start" primary onPress={start} disabled={busy} />
            </View>
          ) : null}

          {ready && screen === "swipe" ? (
            <View>
              <Text style={styles.heading}>Swipe</Text>
              {loading && !current ? <Text style={styles.body}>Loading companies...</Text> : null}
              {!loading && screenLoadError ? (
                <View style={styles.state}>
                  <Text style={styles.body}>{screenLoadError}</Text>
                  <Action label="Try again" primary onPress={retryLoad} />
                </View>
              ) : null}
              {!loading && !screenLoadError && !current ? (
                <View style={styles.state}>
                  <Text style={styles.body}>No more companies right now for the interests you picked. Open Matches, or start over to pick different ones.</Text>
                    <View style={styles.actions}>
                    <Action label="Open Matches" primary fill onPress={() => setScreen("matches")} />
                    <Action label="Start over" fill onPress={askReset} />
                  </View>
                </View>
              ) : null}
              {current && !screenLoadError ? (
                <SwipeableCard
                  key={current.ticker}
                  busy={busy}
                  onSwipe={swipe}
                  onSwipeStart={() => setSwipeScrollEnabled(false)}
                  onSwipeEnd={() => setSwipeScrollEnabled(true)}
                >
                  <View style={styles.card}>
                    <CompanyFacts card={current} showNews />
                    <View style={styles.actions}>
                      <Action label="Like" primary fill onPress={() => swipe("like")} disabled={busy} />
                      <Action label="Pass" fill onPress={() => swipe("dislike")} disabled={busy} />
                    </View>
                  </View>
                </SwipeableCard>
              ) : null}
            </View>
          ) : null}

          {ready && screen === "matches" ? (
            <View>
              <Text style={styles.heading}>Matches</Text>
              {loading ? <Text style={styles.body}>Loading matches...</Text> : null}
              {!loading && screenLoadError ? (
                <View style={styles.state}>
                  <Text style={styles.body}>{screenLoadError}</Text>
                  <Action label="Try again" primary onPress={retryLoad} />
                </View>
              ) : null}
              {!loading && !screenLoadError && matches.length === 0 ? (
                <View style={styles.state}>
                  <Text style={styles.body}>No matches yet. Swipe right or press Like to save a company here.</Text>
                  <Action label="Start swiping" primary onPress={() => setScreen("swipe")} />
                </View>
              ) : null}
              {!screenLoadError ? matches.map((match) => (
                <View style={styles.card} key={match.ticker}>
                  <CompanyFacts card={match} showNews={false} />
                  <Action
                    label="Remove"
                    onPress={() => unlikeMatch(match.ticker)}
                    disabled={unliking === match.ticker}
                  />
                </View>
              )) : null}
            </View>
          ) : null}

          {ready && screen === "updates" ? (
            <View>
              <Text style={styles.heading}>Updates</Text>
              {loading ? <Text style={styles.body}>Loading updates...</Text> : null}
              {!loading && screenLoadError ? (
                <View style={styles.state}>
                  <Text style={styles.body}>{screenLoadError}</Text>
                  <Action label="Try again" primary onPress={retryLoad} />
                </View>
              ) : null}
              {!loading && !screenLoadError ? (
                <UpdatesFeed
                  updates={updates}
                  alerts={alerts}
                  hasLikes={hasLikes}
                  digest={digest}
                  filings={filings}
                  helpers={helpers}
                  styles={styles}
                  onLinkError={setError}
                  emptyAction={{ label: "Start swiping", onPress: () => setScreen("swipe") }}
                />
              ) : null}
            </View>
          ) : null}
        </ScrollView>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

function NavButton({ label, selected, onPress }) {
  return (
    <Pressable
      style={[styles.navBtn, selected ? styles.navBtnOn : null]}
      onPress={onPress}
      accessibilityRole="button"
    >
      <Text style={[styles.navBtnText, selected ? styles.navBtnTextOn : null]} numberOfLines={1}>
        {label}
      </Text>
    </Pressable>
  );
}

function Action({ label, onPress, disabled, primary, fill }) {
  return (
    <Pressable
      style={[
        styles.actionBtn,
        fill ? styles.actionFill : null,
        primary ? styles.primaryBtn : styles.secondaryBtn,
        disabled ? styles.disabled : null,
      ]}
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
    >
      <Text style={primary ? styles.primaryBtnText : styles.secondaryBtnText} numberOfLines={1}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: PAPER,
  },
  content: {
    padding: SPACE.md,
    paddingBottom: 32,
  },
  title: {
    fontSize: TYPE.title,
    fontWeight: "700",
    color: INK,
  },
  tagline: {
    fontSize: TYPE.caption,
    color: INK,
    marginTop: SPACE.sm,
    marginBottom: SPACE.sm,
  },
  body: {
    fontSize: TYPE.body,
    color: INK,
  },
  heading: {
    fontSize: TYPE.title,
    fontWeight: "700",
    color: INK,
    marginTop: SPACE.md,
    marginBottom: SPACE.sm,
  },
  sectionLabel: {
    fontSize: TYPE.title,
    fontWeight: "700",
    color: INK,
    marginTop: SPACE.md,
  },
  alertCard: {
    borderWidth: 1,
    borderColor: LINE,
    borderLeftWidth: 4,
    borderLeftColor: ACCENT,
    backgroundColor: "#fff",
    padding: SPACE.md,
    marginTop: SPACE.md,
  },
  alertLabel: {
    fontSize: TYPE.caption,
    fontWeight: "700",
    color: ACCENT,
    marginBottom: SPACE.sm,
  },
  unseen: {
    fontWeight: "700",
  },
  helper: {
    marginVertical: SPACE.sm,
    fontSize: TYPE.caption,
    fontStyle: "italic",
    color: INK,
  },
  nav: {
    flexDirection: "row",
    flexWrap: "nowrap",
    alignItems: "center",
    gap: SPACE.sm,
    marginTop: SPACE.md,
  },
  navBtn: {
    flex: 1,
    minWidth: 0,
    paddingVertical: SPACE.sm,
    paddingHorizontal: 2,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: LINE,
    backgroundColor: "#fff",
    alignItems: "center",
  },
  navBtnOn: {
    backgroundColor: ACCENT,
    borderColor: ACCENT,
  },
  navBtnText: {
    fontSize: TYPE.caption,
    color: INK,
    textAlign: "center",
  },
  navBtnTextOn: {
    color: "#fff",
    fontWeight: "700",
  },
  choice: {
    fontSize: TYPE.body,
    marginVertical: SPACE.sm,
    color: INK,
  },
  card: {
    borderWidth: 1,
    borderColor: LINE,
    borderRadius: 8,
    backgroundColor: "#fff",
    padding: SPACE.md,
    marginTop: SPACE.md,
  },
  company: {
    fontSize: TYPE.title,
    fontWeight: "700",
    color: INK,
  },
  why: {
    borderLeftWidth: 4,
    borderLeftColor: ACCENT,
    backgroundColor: "rgba(11, 110, 86, 0.12)",
    paddingVertical: SPACE.sm,
    paddingHorizontal: 12,
    marginVertical: SPACE.sm,
  },
  whyLabel: {
    fontSize: TYPE.caption,
    fontWeight: "700",
    color: ACCENT,
    marginBottom: 4,
  },
  row: {
    marginVertical: SPACE.sm,
    fontSize: TYPE.body,
    color: INK,
  },
  link: {
    textDecorationLine: "underline",
    color: ACCENT,
  },
  bold: {
    fontWeight: "700",
  },
  logo: {
    height: 48,
    width: 96,
    marginBottom: SPACE.sm,
  },
  logoFallback: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: "#e7e5e0",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: SPACE.sm,
  },
  logoLetter: {
    fontSize: TYPE.body,
    fontWeight: "700",
    color: "#333",
  },
  banner: {
    marginTop: SPACE.md,
    fontSize: TYPE.body,
    color: INK,
  },
  state: {
    marginTop: SPACE.sm,
  },
  actions: {
    flexDirection: "row",
    flexWrap: "nowrap",
    gap: SPACE.sm,
    marginTop: SPACE.sm,
  },
  actionBtn: {
    minWidth: 0,
    borderRadius: 6,
    paddingVertical: 10,
    paddingHorizontal: 8,
    alignItems: "center",
    marginTop: SPACE.sm,
  },
  actionFill: {
    flex: 1,
  },
  primaryBtn: {
    backgroundColor: ACCENT,
  },
  secondaryBtn: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: LINE,
  },
  primaryBtnText: {
    color: "#fff",
    fontSize: TYPE.body,
    fontWeight: "700",
  },
  secondaryBtnText: {
    color: INK,
    fontSize: TYPE.body,
  },
  disabled: {
    opacity: 0.55,
  },
  error: {
    color: ACCENT,
    fontWeight: "700",
    fontSize: TYPE.body,
    marginVertical: SPACE.sm,
  },
});
