form: "Measure word F0"
    sentence: "wav file", ""
    sentence: "textgrid file", ""
    sentence: "output tsv", ""
    sentence: "tier name", "ORT-MAU"
    real: "pitch floor", "50"
    real: "pitch ceiling", "800"
endform

Read from file: wav_file$
soundID = selected("Sound")
Read from file: textgrid_file$
tgID = selected("TextGrid")

selectObject: soundID
To Pitch (filtered autocorrelation): 0.0, pitch_floor, pitch_ceiling, 15, "no", 0.03, 0.09, 0.50, 0.055, 0.35, 0.14
pitchID = selected("Pitch")

selectObject: tgID
numberOfTiers = Get number of tiers
tier = 0
for tierNumber from 1 to numberOfTiers
    currentTierName$ = Get tier name: tierNumber
    if currentTierName$ = tier_name$
        tier = tierNumber
        goto foundTier
    endif
endfor
label foundTier
if tier = 0
    exitScript: "Tier not found: ", tier_name$
endif

writeFileLine: output_tsv$, "word", tab$, "start", tab$, "end", tab$, "duration", tab$, "mean_f0", tab$, "min_f0", tab$, "max_f0"
nIntervals = Get number of intervals: tier
for i from 1 to nIntervals
    selectObject: tgID
    word$ = Get label of interval: tier, i
    if word$ <> ""
        start = Get start time of interval: tier, i
        finish = Get end time of interval: tier, i
        duration = finish - start

        selectObject: pitchID
        meanF0 = Get mean: start, finish, "Hertz"
        minF0 = Get minimum: start, finish, "Hertz", "Parabolic"
        maxF0 = Get maximum: start, finish, "Hertz", "Parabolic"

        mean$ = if meanF0 = undefined then "0" else fixed$(meanF0, 2) fi
        minimum$ = if minF0 = undefined then "0" else fixed$(minF0, 2) fi
        maximum$ = if maxF0 = undefined then "0" else fixed$(maxF0, 2) fi
        appendFileLine: output_tsv$, word$, tab$, fixed$(start, 6), tab$, fixed$(finish, 6), tab$, fixed$(duration, 3), tab$, mean$, tab$, minimum$, tab$, maximum$
    endif
endfor

selectObject: pitchID, soundID, tgID
Remove
