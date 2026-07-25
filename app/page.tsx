"use client";

import Image from "next/image";
import { useEffect, useMemo, useRef, useState } from "react";
import { CLUB_IDENTITY, HOME_COURSE, NEGATIVE_TAGS, POSITIVE_TAGS, TEE_OPTIONS, teeLabel, type Tee } from "./data/mock-course";
import { MOCK_ROUNDS, type MockRound } from "./data/mock-history";

type Theme = "club" | "sport" | "clean";
type ScoreMethod = "stepper" | "numbers" | "relative";
type RoundLayout = "focus" | "grid";
type TagBehavior = "manual" | "smart";
type NavTab = "home" | "play" | "history" | "settings";
type RoundPhase = "setup" | "active" | "summary";
type CelebrationKind = "birdie" | "eagle";
type CelebrationState = { kind: CelebrationKind; id: number };
type HoleVisualMode = "illustrated" | "aerial";

type HoleEntry = { score?: number; tags: string[]; note: string };
type Entries = Record<number, HoleEntry>;

const STORAGE_KEY = "roundwell-prototype-v2-peach-tree";

const THEME_LABELS: Record<Theme, string> = {
  club: "Private club",
  sport: "Modern sport",
  clean: "Clean",
};

const METHOD_LABELS: Record<ScoreMethod, string> = {
  stepper: "Plus / minus",
  numbers: "Stroke numbers",
  relative: "Relative to par",
};

const formatRelative = (value: number) => (value === 0 ? "E" : value > 0 ? `+${value}` : `${value}`);

const outcomeFor = (score: number, par: number) => {
  const diff = score - par;
  if (diff <= -2) return "Eagle or better";
  if (diff === -1) return "Birdie";
  if (diff === 0) return "Par";
  if (diff === 1) return "Bogey";
  if (diff === 2) return "Double";
  return "Triple+";
};

function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="control-group">
      <span className="control-label">{label}</span>
      <div className="segmented" role="group" aria-label={label}>
        {options.map((option) => (
          <button
            type="button"
            key={option.value}
            className={value === option.value ? "selected" : ""}
            aria-pressed={value === option.value}
            onClick={() => onChange(option.value)}
          >
            {value === option.value && <span aria-hidden="true">✓ </span>}
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function LabControls({
  theme,
  setTheme,
  scoreMethod,
  setScoreMethod,
  roundLayout,
  setRoundLayout,
  tagBehavior,
  setTagBehavior,
}: {
  theme: Theme;
  setTheme: (value: Theme) => void;
  scoreMethod: ScoreMethod;
  setScoreMethod: (value: ScoreMethod) => void;
  roundLayout: RoundLayout;
  setRoundLayout: (value: RoundLayout) => void;
  tagBehavior: TagBehavior;
  setTagBehavior: (value: TagBehavior) => void;
}) {
  return (
    <div className="lab-controls">
      <Segmented
        label="Score entry"
        value={scoreMethod}
        onChange={setScoreMethod}
        options={[
          { value: "stepper", label: "± Stepper" },
          { value: "numbers", label: "Numbers" },
          { value: "relative", label: "To par" },
        ]}
      />
      <Segmented
        label="Round layout"
        value={roundLayout}
        onChange={setRoundLayout}
        options={[
          { value: "focus", label: "One hole" },
          { value: "grid", label: "Scorecard" },
        ]}
      />
      <div className="control-group">
        <span className="control-label">Visual theme</span>
        <div className="theme-grid">
          {(["club", "sport", "clean"] as Theme[]).map((item) => (
            <button
              type="button"
              key={item}
              className={theme === item ? "theme-choice selected" : "theme-choice"}
              aria-pressed={theme === item}
              onClick={() => setTheme(item)}
            >
              <span className={`theme-swatch ${item}`} aria-hidden="true"><i /><i /><i /></span>
              <span>{THEME_LABELS[item]}</span>
              <b>{theme === item ? "Selected" : "Preview"}</b>
            </button>
          ))}
        </div>
      </div>
      <Segmented
        label="Tag behavior"
        value={tagBehavior}
        onChange={setTagBehavior}
        options={[
          { value: "manual", label: "Add details" },
          { value: "smart", label: "Smart reveal" },
        ]}
      />
    </div>
  );
}

function TeePicker({ value, onChange, label = "Tee" }: { value: Tee; onChange: (value: Tee) => void; label?: string }) {
  return (
    <div className="control-group tee-control">
      <span className="control-label">{label}</span>
      <div className="tee-picker" role="group" aria-label={label}>
        {TEE_OPTIONS.map((option) => (
          <button
            type="button"
            key={option.value}
            className={value === option.value ? `selected tee-${option.value}` : `tee-${option.value}`}
            aria-pressed={value === option.value}
            onClick={() => onChange(option.value)}
          >
            <i aria-hidden="true" />
            <span>{option.shortLabel}</span>
            <small>{option.total.toLocaleString()} yd</small>
          </button>
        ))}
      </div>
    </div>
  );
}

export default function GolfTracker() {
  const [theme, setTheme] = useState<Theme>("club");
  const [scoreMethod, setScoreMethod] = useState<ScoreMethod>("stepper");
  const [roundLayout, setRoundLayout] = useState<RoundLayout>("focus");
  const [tagBehavior, setTagBehavior] = useState<TagBehavior>("manual");
  const [nav, setNav] = useState<NavTab>("home");
  const [roundPhase, setRoundPhase] = useState<RoundPhase>("setup");
  const [roundLength, setRoundLength] = useState<9 | 18>(18);
  const [nineSide, setNineSide] = useState<"front" | "back">("front");
  const [tee, setTee] = useState<Tee>("white");
  const [entries, setEntries] = useState<Entries>({});
  const [currentHole, setCurrentHole] = useState(1);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [showLab, setShowLab] = useState(false);
  const [showEndConfirm, setShowEndConfirm] = useState(false);
  const [showHoleGuide, setShowHoleGuide] = useState(false);
  const [holeVisualMode, setHoleVisualMode] = useState<HoleVisualMode>("illustrated");
  const [feedback, setFeedback] = useState("");
  const [celebration, setCelebration] = useState<CelebrationState | null>(null);
  const [handicap, setHandicap] = useState("12.4");
  const [defaultTee, setDefaultTee] = useState<Tee>("white");
  const [defaultLength, setDefaultLength] = useState<9 | 18>(18);
  const [savedRounds, setSavedRounds] = useState<MockRound[]>([]);
  const [selectedHistory, setSelectedHistory] = useState<MockRound | null>(null);
  const [resetConfirm, setResetConfirm] = useState(false);
  const [selectedHoleHistory, setSelectedHoleHistory] = useState<number | null>(null);
  const [savedRoundId, setSavedRoundId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const celebrationIdRef = useRef(0);
  const celebrationTimerRef = useRef<number | null>(null);
  const holeAtlasTriggerRef = useRef<HTMLButtonElement | null>(null);
  const holeGuideDialogRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    ["/celebrations/birdie.png", "/celebrations/eagle.png"].forEach((src) => {
      const image = new window.Image();
      image.src = src;
    });

    return () => {
      if (celebrationTimerRef.current !== null) window.clearTimeout(celebrationTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (!showHoleGuide) return;
    const dialog = holeGuideDialogRef.current;
    const trigger = holeAtlasTriggerRef.current;
    const focusable = dialog?.querySelectorAll<HTMLElement>("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])");
    focusable?.[0]?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setShowHoleGuide(false);
        return;
      }
      if (event.key !== "Tab" || !focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      trigger?.focus();
    };
  }, [showHoleGuide]);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const data = JSON.parse(stored);
        // eslint-disable-next-line react-hooks/set-state-in-effect -- local prototype state hydrates after the client mounts
        if (data.theme) setTheme(data.theme);
        if (data.scoreMethod) setScoreMethod(data.scoreMethod);
        if (data.roundLayout) setRoundLayout(data.roundLayout);
        if (data.tagBehavior) setTagBehavior(data.tagBehavior);
        if (data.handicap) setHandicap(data.handicap);
        if (data.defaultTee) setDefaultTee(data.defaultTee);
        if (data.defaultLength) setDefaultLength(data.defaultLength);
        if (Array.isArray(data.savedRounds)) setSavedRounds(data.savedRounds);
        if (data.activeRound) {
          setRoundPhase(data.activeRound.phase ?? "setup");
          setRoundLength(data.activeRound.roundLength ?? 18);
          setNineSide(data.activeRound.nineSide ?? "front");
          setTee(data.activeRound.tee ?? "white");
          setEntries(data.activeRound.entries ?? {});
          setCurrentHole(data.activeRound.currentHole ?? 1);
          setSavedRoundId(data.activeRound.savedRoundId ?? null);
        }
      }
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        theme,
        scoreMethod,
        roundLayout,
        tagBehavior,
        handicap,
        defaultTee,
        defaultLength,
        savedRounds,
        activeRound: {
          phase: roundPhase,
          roundLength,
          nineSide,
          tee,
          entries,
          currentHole,
          savedRoundId,
        },
      }),
    );
  }, [hydrated, theme, scoreMethod, roundLayout, tagBehavior, handicap, defaultTee, defaultLength, savedRounds, roundPhase, roundLength, nineSide, tee, entries, currentHole, savedRoundId]);

  const scheduledHoles = useMemo(() => {
    if (roundLength === 18) return HOME_COURSE.holes;
    return nineSide === "front" ? HOME_COURSE.holes.slice(0, 9) : HOME_COURSE.holes.slice(9);
  }, [roundLength, nineSide]);

  const hole = HOME_COURSE.holes[currentHole - 1] ?? HOME_COURSE.holes[0];
  const showingIllustration = holeVisualMode === "illustrated" && Boolean(hole.visual.illustratedSrc);
  const activeHoleVisual = showingIllustration
    ? { src: hole.visual.illustratedSrc!, alt: hole.visual.illustratedAlt! }
    : { src: hole.visual.src, alt: hole.visual.alt };
  const holeAtlasLabel = hole.localNote
    ? showingIllustration ? "AI illustrated · local update" : "Local layout update"
    : showingIllustration ? "AI illustrated concept" : HOME_COURSE.guideLabel;
  const currentEntry = entries[currentHole] ?? { tags: [], note: "" };
  const displayedScore = currentEntry.score ?? hole.par;
  const currentIndex = scheduledHoles.findIndex((item) => item.number === currentHole);

  useEffect(() => {
    if (roundPhase !== "active") return;
    const nextHole = scheduledHoles[currentIndex + 1];
    [hole.visual.src, hole.visual.illustratedSrc, nextHole?.visual.src, nextHole?.visual.illustratedSrc].filter(Boolean).forEach((src) => {
      const image = new window.Image();
      image.src = src!;
    });
  }, [currentIndex, hole.visual.illustratedSrc, hole.visual.src, roundPhase, scheduledHoles]);

  const runningRelative = scheduledHoles.reduce((total, item) => {
    const score = entries[item.number]?.score;
    return score ? total + score - item.par : total;
  }, 0);

  const missingHoles = scheduledHoles.filter((item) => !entries[item.number]?.score);
  const combinedRounds = [...savedRounds, ...MOCK_ROUNDS];

  const dismissCelebration = () => {
    if (celebrationTimerRef.current !== null) {
      window.clearTimeout(celebrationTimerRef.current);
      celebrationTimerRef.current = null;
    }
    setCelebration(null);
  };

  const playCelebration = (kind: CelebrationKind) => {
    if (celebrationTimerRef.current !== null) window.clearTimeout(celebrationTimerRef.current);
    const id = celebrationIdRef.current + 1;
    celebrationIdRef.current = id;
    setCelebration({ kind, id });
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    celebrationTimerRef.current = window.setTimeout(() => {
      setCelebration((current) => current?.id === id ? null : current);
      celebrationTimerRef.current = null;
    }, reducedMotion ? 1000 : 2600);
  };

  const recordScore = (rawScore: number) => {
    const score = Math.max(1, Math.min(15, rawScore));
    setEntries((previous) => ({
      ...previous,
      [currentHole]: { ...(previous[currentHole] ?? { tags: [], note: "" }), score },
    }));
    setFeedback(`Saved · ${score} (${outcomeFor(score, hole.par)})`);
    window.setTimeout(() => setFeedback(""), 1600);
    const relativeScore = score - hole.par;
    if (relativeScore <= -2) playCelebration("eagle");
    else if (relativeScore === -1) playCelebration("birdie");
    else dismissCelebration();
  };

  const updateDraftAndRecord = (delta: number) => recordScore(displayedScore + delta);

  const selectHole = (holeNumber: number) => {
    dismissCelebration();
    setShowHoleGuide(false);
    setCurrentHole(holeNumber);
    setDetailsOpen(false);
    setFeedback("");
  };

  const toggleTag = (tag: string) => {
    setEntries((previous) => {
      const item = previous[currentHole] ?? { tags: [], note: "" };
      const tags = item.tags.includes(tag) ? item.tags.filter((value) => value !== tag) : [...item.tags, tag];
      return { ...previous, [currentHole]: { ...item, tags } };
    });
  };

  const updateNote = (note: string) => {
    setEntries((previous) => {
      const item = previous[currentHole] ?? { tags: [], note: "" };
      return { ...previous, [currentHole]: { ...item, note } };
    });
  };

  const startRound = () => {
    dismissCelebration();
    setShowHoleGuide(false);
    const first = roundLength === 9 && nineSide === "back" ? 10 : 1;
    setEntries({});
    setSavedRoundId(null);
    setCurrentHole(first);
    setDetailsOpen(false);
    setRoundPhase("active");
    setRoundLayout("focus");
    setNav("play");
    setFeedback("Round started");
  };

  const moveHole = (offset: number) => {
    const nextIndex = currentIndex + offset;
    if (nextIndex >= 0 && nextIndex < scheduledHoles.length) {
      selectHole(scheduledHoles[nextIndex].number);
    }
  };

  const finishRound = () => {
    dismissCelebration();
    setShowHoleGuide(false);
    if (missingHoles.length > 0) {
      setShowEndConfirm(true);
    } else {
      setRoundPhase("summary");
    }
  };

  const enteredHoles = scheduledHoles.filter((item) => entries[item.number]?.score);
  const finalScore = enteredHoles.reduce((total, item) => total + (entries[item.number]?.score ?? 0), 0);
  const finalRelative = enteredHoles.reduce((total, item) => total + (entries[item.number]!.score! - item.par), 0);
  const frontRelative = scheduledHoles.filter((item) => item.number <= 9 && entries[item.number]?.score).reduce((total, item) => total + (entries[item.number]!.score! - item.par), 0);
  const backRelative = scheduledHoles.filter((item) => item.number > 9 && entries[item.number]?.score).reduce((total, item) => total + (entries[item.number]!.score! - item.par), 0);
  const roundTags = scheduledHoles.flatMap((item) => entries[item.number]?.tags ?? []);
  const countTag = (tag: string) => roundTags.filter((item) => item === tag).length;
  const topPositive = POSITIVE_TAGS.map((tag) => ({ tag, count: countTag(tag) })).filter((item) => item.count).sort((a, b) => b.count - a.count).slice(0, 3);
  const topNegative = NEGATIVE_TAGS.map((tag) => ({ tag, count: countTag(tag) })).filter((item) => item.count).sort((a, b) => b.count - a.count).slice(0, 3);

  const saveRound = (newId: string, date: string) => {
    const id = savedRoundId ?? newId;
    const nextRound: MockRound = {
      id,
      date,
      tee,
      holes: roundLength,
      scoredHoles: enteredHoles.length,
      startingHole: scheduledHoles[0].number,
      score: finalScore,
      toPar: finalRelative,
      holeScores: scheduledHoles.map((item) => entries[item.number]?.score ?? 0),
      tags: roundTags,
    };
    setSavedRounds((previous) => [nextRound, ...previous.filter((item) => item.id !== id)]);
    setSavedRoundId(id);
    setFeedback(savedRoundId ? "Round updated" : "Round saved to this device");
  };

  const resetPrototype = () => {
    dismissCelebration();
    setShowHoleGuide(false);
    window.localStorage.removeItem(STORAGE_KEY);
    setTheme("club");
    setScoreMethod("stepper");
    setRoundLayout("focus");
    setTagBehavior("manual");
    setHandicap("12.4");
    setDefaultTee("white");
    setDefaultLength(18);
    setRoundLength(18);
    setNineSide("front");
    setTee("white");
    setEntries({});
    setSavedRounds([]);
    setRoundPhase("setup");
    setSavedRoundId(null);
    setResetConfirm(false);
    setNav("home");
  };

  const averages = HOME_COURSE.holes.map((courseHole) => {
    const scores = combinedRounds.map((round) => {
      const start = round.startingHole ?? 1;
      return round.holeScores[courseHole.number - start];
    }).filter((score) => score && score > 0);
    const average = scores.length ? scores.reduce((sum, score) => sum + score, 0) / scores.length - courseHole.par : 0;
    return { hole: courseHole, average, samples: scores.slice(0, 5) };
  });
  const bestHoles = [...averages].sort((a, b) => a.average - b.average).slice(0, 3);
  const worstHoles = [...averages].sort((a, b) => b.average - a.average).slice(0, 3);

  const ScoreControls = () => (
    <section className="score-zone" aria-label={`Score hole ${currentHole}`}>
      <div className="score-zone-heading">
        <div>
          <span className="eyebrow">{METHOD_LABELS[scoreMethod]}</span>
          <h2>Record your score</h2>
        </div>
        {currentEntry.score && <span className="score-result">{outcomeFor(currentEntry.score, hole.par)}</span>}
      </div>

      {scoreMethod === "stepper" && (
        <div className="stepper-score">
          <button type="button" aria-label="Subtract one stroke" onClick={() => updateDraftAndRecord(-1)}>−</button>
          <button type="button" className={currentEntry.score ? "score-display recorded" : "score-display"} onClick={() => recordScore(displayedScore)}>
            <strong>{displayedScore}</strong>
            <span>{currentEntry.score ? "strokes · saved" : "tap to record par"}</span>
          </button>
          <button type="button" aria-label="Add one stroke" onClick={() => updateDraftAndRecord(1)}>+</button>
        </div>
      )}

      {scoreMethod === "numbers" && (
        <>
          <div className="score-choice-grid numbers">
            {[2, 3, 4, 5, 6, 7].map((score) => (
              <button key={score} type="button" className={currentEntry.score === score ? "selected" : ""} aria-pressed={currentEntry.score === score} onClick={() => recordScore(score)}>
                <strong>{score}{score === 7 ? "+" : ""}</strong>
                <span>{score === hole.par ? "Par" : score === 7 ? "High score" : outcomeFor(score, hole.par)}</span>
              </button>
            ))}
          </div>
          {currentEntry.score && currentEntry.score >= 7 && (
            <div className="high-score-adjuster">
              <span>Exact score</span>
              <button type="button" aria-label="Lower exact score" onClick={() => recordScore(currentEntry.score! - 1)}>−</button>
              <strong>{currentEntry.score}</strong>
              <button type="button" aria-label="Raise exact score" onClick={() => recordScore(currentEntry.score! + 1)}>+</button>
            </div>
          )}
        </>
      )}

      {scoreMethod === "relative" && (
        <>
          <div className="score-choice-grid relative">
            {[
              { label: "Eagle", diff: -2 },
              { label: "Birdie", diff: -1 },
              { label: "Par", diff: 0 },
              { label: "Bogey", diff: 1 },
              { label: "Double", diff: 2 },
              { label: "Triple+", diff: 3 },
            ].map((option) => {
              const score = Math.max(1, hole.par + option.diff);
              return (
                <button key={option.label} type="button" className={currentEntry.score === score ? "selected" : ""} aria-pressed={currentEntry.score === score} onClick={() => recordScore(score)}>
                  <strong>{option.label}</strong><span>{score} strokes</span>
                </button>
              );
            })}
          </div>
          {currentEntry.score && currentEntry.score >= hole.par + 3 && (
            <div className="high-score-adjuster">
              <span>Triple+ exact</span>
              <button type="button" aria-label="Lower exact score" onClick={() => recordScore(currentEntry.score! - 1)}>−</button>
              <strong>{currentEntry.score}</strong>
              <button type="button" aria-label="Raise exact score" onClick={() => recordScore(currentEntry.score! + 1)}>+</button>
            </div>
          )}
        </>
      )}

      <div className="save-feedback" aria-live="polite">{feedback || (currentEntry.score ? `Saved · ${currentEntry.score} (${outcomeFor(currentEntry.score, hole.par)})` : "Choose a score · no typing needed")}</div>
    </section>
  );

  const TagsPanel = () => {
    const smartOpen = tagBehavior === "smart" && Boolean(currentEntry.score);
    const showTags = detailsOpen || smartOpen;
    const positiveFirst = Boolean(currentEntry.score && currentEntry.score <= hole.par);
    const suggested = positiveFirst ? POSITIVE_TAGS.slice(0, 6) : NEGATIVE_TAGS.slice(0, 6);
    return (
      <section className="details-zone">
        {!showTags && (
          <button type="button" className="details-toggle" onClick={() => setDetailsOpen(true)}>
            <span><b>Add details</b><small>Optional tags and note</small></span><span aria-hidden="true">＋</span>
          </button>
        )}
        {showTags && (
          <>
            <div className="details-heading">
              <div><span className="eyebrow">Optional</span><h3>{tagBehavior === "smart" ? (positiveFirst ? "What went well?" : "What cost a stroke?") : "Performance tags"}</h3></div>
              <button type="button" onClick={() => setDetailsOpen(!detailsOpen)}>{detailsOpen ? "Show less" : "All tags"}</button>
            </div>
            <div className="tag-list">
              {(detailsOpen ? [...POSITIVE_TAGS, ...NEGATIVE_TAGS] : [...suggested]).map((tag) => {
                const selected = currentEntry.tags.includes(tag);
                const positive = POSITIVE_TAGS.includes(tag as (typeof POSITIVE_TAGS)[number]);
                return (
                  <button type="button" key={tag} className={`${positive ? "positive" : "negative"} ${selected ? "selected" : ""}`} aria-pressed={selected} onClick={() => toggleTag(tag)}>
                    {selected ? "✓ " : ""}{tag}
                  </button>
                );
              })}
            </div>
            {detailsOpen && (
              <label className="note-field">
                <span>Optional note</span>
                <textarea value={currentEntry.note} onChange={(event) => updateNote(event.target.value)} placeholder="Only if you want to remember something…" rows={2} />
              </label>
            )}
          </>
        )}
      </section>
    );
  };

  const HomeScreen = () => {
    const comparableRounds = combinedRounds.filter((round) => round.holes === 18 && (round.scoredHoles ?? round.holes) === 18);
    const average = Math.round(comparableRounds.reduce((sum, round) => sum + round.score, 0) / comparableRounds.length);
    const best = Math.min(...comparableRounds.map((round) => round.score));
    const avgRelative = Math.round(comparableRounds.reduce((sum, round) => sum + round.toPar, 0) / comparableRounds.length);
    const maxScore = Math.max(...comparableRounds.map((round) => round.score));
    const minScore = Math.min(...comparableRounds.map((round) => round.score));
    return (
      <div className="screen dashboard-screen">
        <section className="welcome-block">
          <span className="eyebrow">Good afternoon, Mario</span>
          <h1>Your game, one round at a time.</h1>
          <p>Ready for another loop at {CLUB_IDENTITY.wordmark}?</p>
          <button type="button" className="primary-action" onClick={() => { setNav("play"); setRoundPhase("setup"); setRoundLength(defaultLength); setTee(defaultTee); }}>Start a round <span>→</span></button>
        </section>

        <section className="dashboard-section">
          <div className="section-title"><div><span className="eyebrow">Last {combinedRounds.length} rounds</span><h2>Scoring trends</h2></div><button type="button" onClick={() => setNav("history")}>View all</button></div>
          <div className="metric-row">
            <div><span>Average</span><strong>{average}</strong></div>
            <div><span>Best</span><strong>{best}</strong></div>
            <div><span>Avg to par</span><strong>{formatRelative(avgRelative)}</strong></div>
          </div>
          <div className="trend-chart" aria-label="Recent score trend">
            {comparableRounds.slice(0, 7).reverse().map((round) => {
              const height = 24 + ((maxScore - round.score) / Math.max(1, maxScore - minScore)) * 48;
              return <div key={round.id} className="trend-point"><span>{round.score}</span><i style={{ height }} /></div>;
            })}
          </div>
          <div className="recent-rounds">
            {combinedRounds.slice(0, 3).map((round) => (
              <button type="button" key={round.id} onClick={() => { setSelectedHistory(round); setNav("history"); }}>
                <span><b>{round.date}</b><small>{round.scoredHoles && round.scoredHoles < round.holes ? `${round.scoredHoles}/${round.holes} scored` : `${round.holes} holes`} · {teeLabel(round.tee)} tees</small></span>
                <strong>{round.score}<small>{formatRelative(round.toPar)}</small></strong>
              </button>
            ))}
          </div>
        </section>

        <section className="dashboard-section insights-section">
          <div className="section-title"><div><span className="eyebrow">Directional, not strokes gained</span><h2>What your tags suggest</h2></div></div>
          {[
            ["Driving", 74, "Strength", "Fairways are trending up"],
            ["Approach", 43, "Watch", "Missed green appears most often"],
            ["Short game", 62, "Steady", "Three recent up-and-downs"],
            ["Putting", 48, "Watch", "Three-putts drove two doubles"],
            ["Decisions", 68, "Steady", "Few penalty or strategy tags"],
          ].map(([label, value, status, insight]) => (
            <div className="insight-row" key={label as string}>
              <div><b>{label}</b><span>{insight}</span></div>
              <div className="insight-meter"><i style={{ width: `${value}%` }} /></div>
              <strong>{status}</strong>
            </div>
          ))}
        </section>

        <section className="dashboard-section holes-section">
          <div className="section-title"><div><span className="eyebrow">{HOME_COURSE.shortName}</span><h2>Best & toughest holes</h2></div></div>
          <div className="hole-rank-columns">
            <div><h3>Best</h3>{bestHoles.map((item, index) => <button type="button" key={item.hole.number} onClick={() => setSelectedHoleHistory(item.hole.number)}><span>{index + 1}</span><b>Hole {item.hole.number}<small>Par {item.hole.par}</small></b><strong>{formatRelative(Number(item.average.toFixed(1)))}</strong></button>)}</div>
            <div><h3>Toughest</h3>{worstHoles.map((item, index) => <button type="button" key={item.hole.number} onClick={() => setSelectedHoleHistory(item.hole.number)}><span>{index + 1}</span><b>Hole {item.hole.number}<small>Par {item.hole.par}</small></b><strong>{formatRelative(Number(item.average.toFixed(1)))}</strong></button>)}</div>
          </div>
        </section>
      </div>
    );
  };

  const SetupScreen = () => (
    <div className="screen setup-screen">
      <div className="page-heading"><span className="eyebrow">New round</span><h1>Let’s play.</h1><p>Three choices, then straight to the first tee.</p></div>
      <section className="course-banner course-banner-aerial">
        <Image src={HOME_COURSE.aerial} alt={`Aerial overview of ${CLUB_IDENTITY.fullName} in ${CLUB_IDENTITY.location}`} fill sizes="(max-width: 560px) 100vw, 560px" priority unoptimized />
        <span className="course-banner-shade" aria-hidden="true" />
        <div className="course-mark" aria-hidden="true"><span>{HOME_COURSE.monogram}</span></div>
        <div className="course-banner-copy"><span className="eyebrow">Home course · {CLUB_IDENTITY.locality}</span><h2>{HOME_COURSE.name}</h2><p>{HOME_COURSE.address}</p></div>
        <span className="course-par">PAR<br /><b>{HOME_COURSE.par}</b></span>
      </section>
      <section className="setup-options">
        <Segmented label="Round length" value={String(roundLength) as "9" | "18"} onChange={(value) => setRoundLength(Number(value) as 9 | 18)} options={[{ value: "9", label: "9 holes" }, { value: "18", label: "18 holes" }]} />
        {roundLength === 9 && <Segmented label="Which nine?" value={nineSide} onChange={setNineSide} options={[{ value: "front", label: "Front 9" }, { value: "back", label: "Back 9" }]} />}
        <TeePicker value={tee} onChange={setTee} />
      </section>
      <div className="scorecard-source-note">{HOME_COURSE.scorecardNote}</div>
      <div className="setup-summary"><span>{roundLength} holes</span><i />{roundLength === 9 && <><span>{nineSide === "front" ? "Front nine" : "Back nine"}</span><i /></>}<span>{teeLabel(tee)} tees</span></div>
      <button type="button" className="primary-action start-button" onClick={startRound}>Start round <span>→</span></button>
    </div>
  );

  const GridScorecard = () => (
    <section className="grid-scorecard">
      <div className="scorecard-splits"><span>OUT <b>{formatRelative(frontRelative)}</b></span>{roundLength === 18 && <span>IN <b>{formatRelative(backRelative)}</b></span>}<span>ROUND <b>{formatRelative(runningRelative)}</b></span></div>
      <div className="holes-grid">
        {scheduledHoles.map((item) => {
          const entry = entries[item.number];
          const isCurrent = item.number === currentHole;
          return (
            <button type="button" key={item.number} className={`${isCurrent ? "current" : ""} ${entry?.score ? "scored" : "unscored"}`} onClick={() => selectHole(item.number)} aria-label={`Hole ${item.number}, par ${item.par}, ${entry?.score ? `score ${entry.score}` : "unscored"}${isCurrent ? ", current" : ""}`}>
              <span>H{item.number}</span><strong>{entry?.score ?? "—"}</strong><small>PAR {item.par}</small>
            </button>
          );
        })}
      </div>
    </section>
  );

  const ActiveRound = () => (
    <div className="screen active-round-screen">
      <header className="round-header">
        <div><span className="eyebrow">{HOME_COURSE.shortName}</span><p>{roundLength} holes · {teeLabel(tee)} tees</p></div>
        <div className="round-header-actions"><button type="button" onClick={() => setShowLab(true)}>◫ Lab</button><button type="button" onClick={finishRound}>End</button></div>
      </header>

      <button ref={holeAtlasTriggerRef} type="button" className="hole-atlas-card" onClick={() => setShowHoleGuide(true)} aria-label={`Open course guide for hole ${currentHole}`}>
        <Image src={activeHoleVisual.src} alt={activeHoleVisual.alt} fill sizes="(max-width: 560px) 100vw, 560px" priority unoptimized />
        <span className="hole-atlas-shade" aria-hidden="true" />
        <span className="hole-atlas-kicker"><b>{holeAtlasLabel}</b><em>{hole.visual.illustratedSrc ? "Compare views ↗" : "View hole ↗"}</em></span>
        <span className="hole-atlas-content">
          <span className="hole-atlas-ident"><small>Hole</small><strong>{currentHole}</strong></span>
          <span className="hole-atlas-facts"><b>PAR <strong>{hole.par}</strong></b><b>{teeLabel(tee).toUpperCase()} <strong>{hole.yardages[tee]} yd</strong></b><b>HCP <strong>{hole.strokeIndex}</strong></b></span>
          <span className="hole-atlas-round"><small>Round</small><strong>{formatRelative(runningRelative)}</strong></span>
        </span>
      </button>

      {roundLayout === "grid" && GridScorecard()}
      {ScoreControls()}
      {TagsPanel()}

      <div className="round-dock" aria-label="Round navigation">
        <button type="button" onClick={() => moveHole(-1)} disabled={currentIndex <= 0}><span aria-hidden="true">←</span><small>Previous</small></button>
        <button type="button" className="scorecard-toggle" onClick={() => setRoundLayout(roundLayout === "focus" ? "grid" : "focus")}><span aria-hidden="true">{roundLayout === "focus" ? "▦" : "●"}</span><small>{roundLayout === "focus" ? "Scorecard" : "Current hole"}</small></button>
        <button type="button" className="next-hole" onClick={() => currentIndex === scheduledHoles.length - 1 ? finishRound() : moveHole(1)}><span aria-hidden="true">→</span><small>{currentIndex === scheduledHoles.length - 1 ? "Finish" : "Next hole"}</small></button>
      </div>
    </div>
  );

  const SummaryScreen = () => {
    const counts = { birdies: 0, pars: 0, bogeys: 0, doubles: 0, triples: 0 };
    enteredHoles.forEach((item) => {
      const diff = entries[item.number]!.score! - item.par;
      if (diff < 0) counts.birdies += 1;
      else if (diff === 0) counts.pars += 1;
      else if (diff === 1) counts.bogeys += 1;
      else if (diff === 2) counts.doubles += 1;
      else counts.triples += 1;
    });
    return (
      <div className="screen summary-screen">
        <div className="summary-hero"><span className="eyebrow">Round complete</span><div><strong>{finalScore || "—"}</strong><span><b>{formatRelative(finalRelative)}</b>{enteredHoles.length} of {scheduledHoles.length} holes scored</span></div><p>{missingHoles.length ? `${missingHoles.length} holes left unscored` : "Card complete"} · {teeLabel(tee)} tees</p></div>
        <section className="summary-splits"><div><span>Front nine</span><strong>{formatRelative(frontRelative)}</strong></div>{roundLength === 18 && <div><span>Back nine</span><strong>{formatRelative(backRelative)}</strong></div>}<div><span>Total</span><strong>{formatRelative(finalRelative)}</strong></div></section>
        <section className="summary-section"><div className="section-title"><div><span className="eyebrow">Hole by hole</span><h2>Your scorecard</h2></div></div><div className="mini-scorecard">{scheduledHoles.map((item) => <div key={item.number}><span>{item.number}</span><strong>{entries[item.number]?.score ?? "—"}</strong><small>{item.par}</small></div>)}</div><div className="scorecard-key"><span>Hole</span><span>Score</span><span>Par</span></div></section>
        <section className="summary-section"><div className="section-title"><div><span className="eyebrow">Scoring mix</span><h2>How it happened</h2></div></div><div className="outcome-grid">{[["Birdie+", counts.birdies], ["Pars", counts.pars], ["Bogeys", counts.bogeys], ["Doubles", counts.doubles], ["Triple+", counts.triples]].map(([label, count]) => <div key={label}><strong>{count}</strong><span>{label}</span></div>)}</div></section>
        <section className="summary-section"><div className="section-title"><div><span className="eyebrow">Based on your optional tags</span><h2>Where strokes were lost</h2></div></div><p className="lost-summary">{topNegative.length ? `${topNegative.map((item) => item.tag).join(", ")} appeared most often. That points to a useful practice theme, not formal strokes-gained analysis.` : "Add a few performance tags during the round and this area will surface the most common patterns."}</p><div className="tag-summary"><div><h3>Positive</h3>{topPositive.length ? topPositive.map((item) => <span key={item.tag}>+ {item.tag} · {item.count}</span>) : <span>No positive tags yet</span>}</div><div><h3>Needs attention</h3>{topNegative.length ? topNegative.map((item) => <span key={item.tag}>− {item.tag} · {item.count}</span>) : <span>No negative tags yet</span>}</div></div></section>
        <div className="summary-actions"><button type="button" className="primary-action" onClick={() => { const timestamp = Date.now(); saveRound(`saved-${timestamp}`, new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(new Date(timestamp))); }}>{savedRoundId ? "Update saved round" : "Save round"}</button><button type="button" className="secondary-action" onClick={() => { setFeedback(""); setRoundPhase("active"); }}>Edit round</button>{feedback && <span className="save-feedback" aria-live="polite">{feedback}</span>}</div>
      </div>
    );
  };

  const HistoryScreen = () => {
    if (selectedHistory) {
      return (
        <div className="screen history-detail">
          <button type="button" className="back-link" onClick={() => setSelectedHistory(null)}>← Round history</button>
          <div className="page-heading"><span className="eyebrow">{selectedHistory.date}</span><h1>{selectedHistory.score} <small>{formatRelative(selectedHistory.toPar)}</small></h1><p>{HOME_COURSE.name} · {selectedHistory.scoredHoles && selectedHistory.scoredHoles < selectedHistory.holes ? `${selectedHistory.scoredHoles}/${selectedHistory.holes} scored` : `${selectedHistory.holes} holes`} · {teeLabel(selectedHistory.tee)} tees</p></div>
          <div className="mini-scorecard large">{selectedHistory.holeScores.map((score, index) => { const holeNumber = (selectedHistory.startingHole ?? 1) + index; return <div key={holeNumber}><span>{holeNumber}</span><strong>{score || "—"}</strong><small>{HOME_COURSE.holes[holeNumber - 1]?.par ?? ""}</small></div>; })}</div>
          <section className="summary-section"><div className="section-title"><div><span className="eyebrow">Round notes</span><h2>Performance tags</h2></div></div><div className="tag-list readonly">{selectedHistory.tags.map((tag) => <span key={tag}>{tag}</span>)}</div></section>
          <section className="summary-section"><p className="lost-summary">This prototype uses your selected tags to show directional patterns. It does not calculate formal strokes-gained values.</p></section>
        </div>
      );
    }
    return (
      <div className="screen history-screen">
        <div className="page-heading"><span className="eyebrow">Your archive</span><h1>Round history</h1><p>{combinedRounds.length} rounds stored in this prototype.</p></div>
        <div className="history-list">
          {combinedRounds.map((round) => (
            <button type="button" key={round.id} onClick={() => setSelectedHistory(round)}>
              <span className="date-tile"><b>{round.date.split(" ")[1]?.replace(",", "")}</b><small>{round.date.split(" ")[0]}</small></span>
              <span className="history-main"><b>{HOME_COURSE.name}</b><small>{round.scoredHoles && round.scoredHoles < round.holes ? `${round.scoredHoles}/${round.holes} scored` : `${round.holes} holes`} · {teeLabel(round.tee)} tees</small></span>
              <span className="history-score"><b>{round.score}</b><small>{formatRelative(round.toPar)}</small></span>
              <span aria-hidden="true">›</span>
            </button>
          ))}
        </div>
      </div>
    );
  };

  const SettingsScreen = () => (
    <div className="screen settings-screen">
      <div className="page-heading"><span className="eyebrow">Profile & prototype</span><h1>Settings</h1><p>Personalize defaults without complicating live scoring.</p></div>
      <section className="settings-section">
        <div className="section-title"><div><span className="eyebrow">Golfer</span><h2>Profile</h2></div></div>
        <label className="settings-input"><span><b>Stored handicap</b><small>For reference only · no net scoring yet</small></span><input value={handicap} onChange={(event) => setHandicap(event.target.value)} inputMode="decimal" aria-label="Stored handicap" /></label>
        <TeePicker label="Default tee" value={defaultTee} onChange={setDefaultTee} />
        <Segmented label="Default round" value={String(defaultLength) as "9" | "18"} onChange={(value) => setDefaultLength(Number(value) as 9 | 18)} options={[{ value: "9", label: "9 holes" }, { value: "18", label: "18 holes" }]} />
      </section>
      <section className="settings-section">
        <div className="section-title"><div><span className="eyebrow">Compare options</span><h2>Prototype Lab</h2></div><span className="lab-status">{METHOD_LABELS[scoreMethod]} · {roundLayout === "focus" ? "One hole" : "Grid"}</span></div>
        <LabControls theme={theme} setTheme={setTheme} scoreMethod={scoreMethod} setScoreMethod={setScoreMethod} roundLayout={roundLayout} setRoundLayout={setRoundLayout} tagBehavior={tagBehavior} setTagBehavior={setTagBehavior} />
      </section>
      <section className="settings-section danger-zone"><div><b>Reset prototype data</b><p>Clear saved rounds, the active round, profile values, and Lab choices on this device.</p></div>{resetConfirm ? <div className="confirm-row"><button type="button" onClick={() => setResetConfirm(false)}>Cancel</button><button type="button" className="danger" onClick={resetPrototype}>Yes, reset everything</button></div> : <button type="button" onClick={() => setResetConfirm(true)}>Clear / reset mock data</button>}</section>
    </div>
  );

  const showStandardChrome = !(nav === "play" && roundPhase === "active");

  return (
    <main className="app-shell" data-theme={theme}>
      <div className="app-frame">
        {showStandardChrome && (
          <header className="app-header">
            <button type="button" className="brand" onClick={() => { setNav("home"); setSelectedHistory(null); }} aria-label={`${CLUB_IDENTITY.wordmark} home`}><span className="brand-mark"><Image src="/icons/crest-84.png" alt="" width={42} height={42} priority unoptimized /></span><span><b>{CLUB_IDENTITY.wordmark}</b><small>{CLUB_IDENTITY.headerSubtitle}</small></span></button>
            <button type="button" className="lab-pill" onClick={() => setShowLab(true)}>◫ Prototype Lab</button>
          </header>
        )}

        {nav === "home" && HomeScreen()}
        {nav === "play" && roundPhase === "setup" && SetupScreen()}
        {nav === "play" && roundPhase === "active" && ActiveRound()}
        {nav === "play" && roundPhase === "summary" && SummaryScreen()}
        {nav === "history" && HistoryScreen()}
        {nav === "settings" && SettingsScreen()}

        {showStandardChrome && (
          <nav className="bottom-nav" aria-label="Primary navigation">
            {[
              { id: "home" as NavTab, icon: "⌂", label: "Home" },
              { id: "play" as NavTab, icon: "●", label: "Play" },
              { id: "history" as NavTab, icon: "≡", label: "History" },
              { id: "settings" as NavTab, icon: "⚙", label: "Settings" },
            ].map((item) => <button type="button" key={item.id} className={nav === item.id ? "selected" : ""} aria-current={nav === item.id ? "page" : undefined} onClick={() => { setNav(item.id); setSelectedHistory(null); }}><span aria-hidden="true">{item.icon}</span><small>{item.label}</small></button>)}
          </nav>
        )}

        {celebration && (
          <div key={celebration.id} className={`score-celebration ${celebration.kind}`} aria-hidden="true">
            <div className="celebration-vignette" />
            <div className="celebration-halo"><i /><i /></div>
            <div className="celebration-sparks">
              {Array.from({ length: 12 }, (_, index) => <i key={index} />)}
            </div>
            <div className="celebration-stage">
              <div className="celebration-art">
                <Image
                  src={`/celebrations/${celebration.kind}.png`}
                  alt=""
                  fill
                  sizes="(max-width: 560px) 100vw, 560px"
                  priority
                  unoptimized
                />
              </div>
              <div className="celebration-copy">
                <span>{celebration.kind === "birdie" ? "One under" : "Two under or better"}</span>
                <strong>{celebration.kind === "birdie" ? "BIRDIE" : "EAGLE"}</strong>
                <small>{celebration.kind === "birdie" ? "Beautifully done." : "That deserves a moment."}</small>
              </div>
            </div>
          </div>
        )}

        {showLab && (
          <div className="modal-layer" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) setShowLab(false); }}>
            <section className="bottom-sheet" role="dialog" aria-modal="true" aria-labelledby="lab-title">
              <div className="sheet-handle" aria-hidden="true" />
              <div className="sheet-heading"><div><span className="eyebrow">Compare without losing your round</span><h2 id="lab-title">Prototype Lab</h2></div><button type="button" aria-label="Close Prototype Lab" onClick={() => setShowLab(false)}>×</button></div>
              <LabControls theme={theme} setTheme={setTheme} scoreMethod={scoreMethod} setScoreMethod={setScoreMethod} roundLayout={roundLayout} setRoundLayout={setRoundLayout} tagBehavior={tagBehavior} setTagBehavior={setTagBehavior} />
              <button type="button" className="primary-action" onClick={() => setShowLab(false)}>Apply & close</button>
            </section>
          </div>
        )}

        {showHoleGuide && (
          <div className="modal-layer hole-guide-layer" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) setShowHoleGuide(false); }}>
            <section ref={holeGuideDialogRef} className="bottom-sheet hole-guide-sheet" role="dialog" aria-modal="true" aria-labelledby="hole-guide-title">
              <div className="sheet-handle" aria-hidden="true" />
              <div className="sheet-heading">
                <div><span className="eyebrow">{holeAtlasLabel}</span><h2 id="hole-guide-title">Hole {currentHole} course guide</h2></div>
                <button type="button" aria-label="Close hole course guide" onClick={() => setShowHoleGuide(false)}>×</button>
              </div>
              {hole.visual.illustratedSrc && (
                <div className="hole-guide-mode" role="group" aria-label="Hole image style">
                  <button type="button" className={holeVisualMode === "illustrated" ? "selected" : ""} aria-pressed={holeVisualMode === "illustrated"} onClick={() => setHoleVisualMode("illustrated")}><span>Illustrated</span><small>AI concept</small></button>
                  <button type="button" className={holeVisualMode === "aerial" ? "selected" : ""} aria-pressed={holeVisualMode === "aerial"} onClick={() => setHoleVisualMode("aerial")}><span>Aerial</span><small>2022 source</small></button>
                </div>
              )}
              <div className="hole-guide-visual">
                <Image src={activeHoleVisual.src} alt={activeHoleVisual.alt} fill sizes="(max-width: 560px) 100vw, 560px" unoptimized />
                <span className="hole-guide-vignette" aria-hidden="true" />
                <span className="hole-guide-marker green">Green</span>
                <span className="hole-guide-marker tee">Tee</span>
              </div>
              <div className="hole-guide-primary-facts">
                <span><small>Hole</small><strong>{currentHole}</strong></span>
                <span><small>Par</small><strong>{hole.par}</strong></span>
                <span><small>{teeLabel(tee)}</small><strong>{hole.yardages[tee]} <em>yd</em></strong></span>
                <span><small>Handicap</small><strong>{hole.strokeIndex}</strong></span>
              </div>
              <div className="hole-guide-tees" aria-label={`Hole ${currentHole} tee yardages`}>
                {TEE_OPTIONS.map((option) => <span key={option.value} className={option.value === tee ? "selected" : ""}><i className={`tee-dot tee-${option.value}`} aria-hidden="true" /><small>{option.shortLabel}</small><b>{hole.yardages[option.value]}</b></span>)}
              </div>
              {hole.localNote && <div className="hole-local-note"><span>Local course update</span><b>Hole {hole.number} has changed since this aerial.</b><p>{hole.localNote}</p></div>}
              <div className="hole-guide-note">
                <b>{showingIllustration ? "A premium concept grounded in the real hole." : "Read the real shape before you play."}</b>
                <p>{showingIllustration ? "This AI interpretation uses the aerial as its layout reference, then adds modeled trees, terrain, fairway cuts, and cinematic light. Compare it with the source before treating any detail as exact." : "This aerial preserves the course corridor, tree lines, bunker positions, and surrounding hazards. Use it as a visual planning aid—not as live GPS or a pin sheet."}</p>
              </div>
              <p className="hole-guide-credit">{HOME_COURSE.scorecardNote}<br />{HOME_COURSE.guideCredit}</p>
              <button type="button" className="primary-action" onClick={() => setShowHoleGuide(false)}>Back to scoring</button>
            </section>
          </div>
        )}

        {selectedHoleHistory && (
          <div className="modal-layer" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) setSelectedHoleHistory(null); }}>
            <section className="bottom-sheet compact" role="dialog" aria-modal="true" aria-labelledby="hole-history-title">
              <div className="sheet-handle" aria-hidden="true" />
              <div className="hole-history-aerial">
                <Image src={HOME_COURSE.holes[selectedHoleHistory - 1].visual.illustratedSrc ?? HOME_COURSE.holes[selectedHoleHistory - 1].visual.src} alt={HOME_COURSE.holes[selectedHoleHistory - 1].visual.illustratedAlt ?? HOME_COURSE.holes[selectedHoleHistory - 1].visual.alt} fill sizes="(max-width: 560px) 100vw, 560px" unoptimized />
                <span aria-hidden="true">Hole {selectedHoleHistory}</span>
              </div>
              <span className="eyebrow">{HOME_COURSE.shortName} · recent rounds</span>
              <h2 id="hole-history-title">Hole {selectedHoleHistory} history</h2>
              <p>Par {HOME_COURSE.holes[selectedHoleHistory - 1].par} · {HOME_COURSE.holes[selectedHoleHistory - 1].yardages[defaultTee]} yd from {teeLabel(defaultTee)} · average {formatRelative(Number(averages[selectedHoleHistory - 1].average.toFixed(1)))}</p>
              <div className="hole-history-samples">
                {averages[selectedHoleHistory - 1].samples.map((score, index) => <span key={`${score}-${index}`}><small>Round {index + 1}</small><b>{score}</b><em>{formatRelative(score - HOME_COURSE.holes[selectedHoleHistory - 1].par)}</em></span>)}
              </div>
              <button type="button" className="primary-action" onClick={() => setSelectedHoleHistory(null)}>Close hole history</button>
            </section>
          </div>
        )}

        {showEndConfirm && (
          <div className="modal-layer">
            <section className="bottom-sheet compact" role="alertdialog" aria-modal="true" aria-labelledby="end-title">
              <div className="sheet-handle" aria-hidden="true" />
              <div className="end-icon" aria-hidden="true">{missingHoles.length}</div>
              <h2 id="end-title">{missingHoles.length} {missingHoles.length === 1 ? "hole is" : "holes are"} still missing</h2>
              <p>You can keep scoring, or finish now. Missing holes will stay blank in your summary.</p>
              <button type="button" className="primary-action" onClick={() => setShowEndConfirm(false)}>Keep scoring</button>
              <button type="button" className="secondary-action" onClick={() => { setShowEndConfirm(false); setRoundPhase("summary"); }}>Finish anyway</button>
            </section>
          </div>
        )}
      </div>
    </main>
  );
}
