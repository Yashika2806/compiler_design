import { useCallback, useEffect, useState } from 'react'

// Shared play / pause / step logic for the phase replays.
// `playable` = ascending list of step indexes that Next/Back/Play may stop on.
export default function usePlayer(playable, lastIdx, initialSpeed = 6) {
  const [cur, setCur] = useState(-1)
  const [playing, setPlaying] = useState(true)
  const [speed, setSpeed] = useState(initialSpeed)

  const nextOf = useCallback((c) => playable.find((i) => i > c) ?? c, [playable])
  const prevOf = useCallback((c) => {
    for (let k = playable.length - 1; k >= 0; k--) if (playable[k] < c) return playable[k]
    return -1
  }, [playable])

  useEffect(() => {
    if (!playing) return undefined
    const id = setInterval(() => setCur((c) => nextOf(c)), 1000 / speed)
    return () => clearInterval(id)
  }, [playing, speed, nextOf])

  useEffect(() => { if (playing && cur >= lastIdx) setPlaying(false) }, [cur, playing, lastIdx])

  const finished = cur >= lastIdx
  const jump = (i) => { setPlaying(false); setCur(i) }
  return { cur, setCur, playing, setPlaying, speed, setSpeed, nextOf, prevOf, finished, jump }
}
