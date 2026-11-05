import { useEffect, useRef, useState } from "react";
import { StatusBar } from "expo-status-bar";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import {
  Alert,
  Animated,
  Button,
  Image,
  PanResponder,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import {
  dislikeCompany,
  getCards,
  getHealth,
  getMatches,
  likeCompany,
  onboard,
} from "./api";
import { becauseLikedText, nextQueueAfterLike, priceLine } from "./cardText";

const USER_KEY = "fund_user_id";
const SWIPE_THRESHOLD = 120;

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
        <Text style={styles.bold}>Latest news:</Text> unavailable
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

function CompanyFacts({ card, showNews }) {
  // holder_count is omitted by the API and stays off the card, same as the website.
  return (
    <View>
      {card.logo_url ? (
        <Image source={{ uri: card.logo_url }} style={styles.logo} resizeMode="contain" />
      ) : null}
      <Text style={styles.company}>
        {card.company_name} ({card.ticker})
      </Text>
      <Why line={card.why_line} />
      <BecauseLiked card={card} />
      <Text style={styles.row}>{priceLine(card)}</Text>
      <Text style={styles.row}>{card.short_description}</Text>
      {showNews ? <NewsBlock card={card} /> : null}
      {showNews ? (
        <Text style={styles.row}>{card.quarterly_summary || "Latest quarter: unavailable"}</Text>
      ) : null}
      {showNews ? (
        <Text style={styles.row}>{card.quarter_label || "Last quarter: unavailable"}</Text>
      ) : null}
    </View>
  );
}

function SwipeableCard({ busy, onSwipe, children }) {
  const pan = useRef(new Animated.ValueXY()).current;
  const onSwipeRef = useRef(onSwipe);
  const busyRef = useRef(busy);
  const locked = useRef(false);
  onSwipeRef.current = onSwipe;
  busyRef.current = busy;

  function springBack() {
    Animated.spring(pan, {
      toValue: { x: 0, y: 0 },
      useNativeDriver: false,
    }).start();
  }

  const responder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponderCapture: (_, gesture) => {
        if (busyRef.current || locked.current) return false;
        return Math.abs(gesture.dx) > 12 && Math.abs(gesture.dx) > Math.abs(gesture.dy);
      },
      onPanResponderMove: (_, gesture) => {
        if (busyRef.current || locked.current) return;
        pan.setValue({ x: gesture.dx, y: gesture.dy * 0.2 });
      },
      onPanResponderRelease: (_, gesture) => {
        let action = "";
        let toX = 0;
        if (gesture.dx > SWIPE_THRESHOLD) {
          action = "like";
          toX = 500;
        } else if (gesture.dx < -SWIPE_THRESHOLD) {
          action = "dislike";
          toX = -500;
        }
        if (!action || busyRef.current || locked.current) {
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
      },
      onPanResponderTerminate: () => {
        springBack();
      },
    })
  ).current;

  return (
    <Animated.View
      style={{ transform: [{ translateX: pan.x }, { translateY: pan.y }] }}
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
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [finnhub, setFinnhub] = useState("off");
  const swipeLock = useRef(false);

  useEffect(() => {
    let cancelled = false;
    AsyncStorage.getItem(USER_KEY)
      .then((stored) => {
        if (cancelled || !stored) return;
        setUserId(stored);
        setScreen("swipe");
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || "Could not read the saved session.");
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
  }, [ready, screen, userId]);

  useEffect(() => {
    if (!ready || screen !== "matches" || !userId) return undefined;
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
  }, [ready, screen, userId]);

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
    setPicked([]);
    setScreen("onboarding");
    setError(message || "");
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

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.screen} edges={["top", "bottom", "left", "right"]}>
        <StatusBar style="dark" />
        <ScrollView contentContainerStyle={styles.content}>
          <Text style={styles.title}>fun(d)</Text>
          <Text>Swipe stocks that match what you already care about.</Text>

          {ready && userId ? (
            <View style={styles.nav}>
              <Button title="Swipe" onPress={() => setScreen("swipe")} />
              <Button title="Matches" onPress={() => setScreen("matches")} />
              <Button title="Start over" onPress={askReset} />
            </View>
          ) : null}

          {finnhub === "off" && screen !== "onboarding" ? (
            <Text style={styles.row}>
              Live price and news are unavailable until a Finnhub key is added.
            </Text>
          ) : null}

          {error ? <Text style={styles.error}>{error}</Text> : null}

          {ready && screen === "onboarding" ? (
            <View>
              <Text style={styles.heading}>What are you into?</Text>
              <Text>Pick one or more. You can change this later with Start over.</Text>
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
              <Button title="Start" onPress={start} disabled={busy} />
            </View>
          ) : null}

          {ready && screen === "swipe" ? (
            <View>
              <Text style={styles.heading}>Swipe</Text>
              {loading && !current ? <Text>Loading a company...</Text> : null}
              {!loading && !current ? (
                <Text>No more companies for your interests. Open Matches, or start over and pick different interests.</Text>
              ) : null}
              {current ? (
                <SwipeableCard key={current.ticker} busy={busy} onSwipe={swipe}>
                  <View style={styles.card}>
                    <CompanyFacts card={current} showNews />
                    <Button title="Like" onPress={() => swipe("like")} disabled={busy} />
                    <Button title="Dislike" onPress={() => swipe("dislike")} disabled={busy} />
                  </View>
                </SwipeableCard>
              ) : null}
            </View>
          ) : null}

          {ready && screen === "matches" ? (
            <View>
              <Text style={styles.heading}>Matches</Text>
              {loading ? <Text>Loading matches...</Text> : null}
              {!loading && matches.length === 0 ? (
                <Text>No matches yet. Tap Like on a company you'd like to follow and it'll show up here.</Text>
              ) : null}
              {matches.map((match) => (
                <View style={styles.card} key={match.ticker}>
                  <CompanyFacts card={match} showNews={false} />
                </View>
              ))}
            </View>
          ) : null}
        </ScrollView>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#f4f1ea",
  },
  content: {
    padding: 16,
    paddingBottom: 32,
  },
  title: {
    fontSize: 32,
    fontWeight: "700",
    marginBottom: 4,
  },
  heading: {
    fontSize: 22,
    fontWeight: "700",
    marginTop: 16,
    marginBottom: 8,
  },
  nav: {
    marginTop: 12,
  },
  choice: {
    fontSize: 18,
    marginVertical: 8,
  },
  card: {
    borderWidth: 2,
    borderColor: "#111",
    backgroundColor: "#fff",
    padding: 16,
    marginTop: 12,
  },
  company: {
    fontSize: 20,
    fontWeight: "700",
  },
  why: {
    borderWidth: 4,
    borderColor: "#111",
    backgroundColor: "#fff3a0",
    padding: 12,
    marginVertical: 12,
  },
  whyLabel: {
    fontWeight: "700",
    textTransform: "uppercase",
    marginBottom: 4,
  },
  row: {
    marginVertical: 8,
  },
  bold: {
    fontWeight: "700",
  },
  logo: {
    height: 48,
    width: 96,
    marginBottom: 8,
  },
  error: {
    color: "#8a1f1f",
    fontWeight: "700",
    marginVertical: 8,
  },
});
