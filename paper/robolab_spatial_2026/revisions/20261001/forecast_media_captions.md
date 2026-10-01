# Proposed captions for the forecast media figures

These captions are for the paper agent to integrate. They are proposals: `revision_esmaeil.tex` and `main.tex` are unchanged. `revision_esmaeil.tex` already sets `\graphicspath{{revision_assets/}{figures/}}`, so the bare file names below resolve.

- **Use the PDFs.** They embed the source pixels without resampling. The PNGs are 250 dpi previews.
- **Size.** Each figure is 7.2 in wide; use `width=\linewidth`.
- **Facts.** Every number and path in these captions is in `forecast_media_provenance.json`.
- **Background.** See `forecast_media_README.md`.

## Figure: Cosmos3 Edge example

```latex
\begin{figure}[t]
\centering
\includegraphics[width=\linewidth]{rev_forecast_example_edge.pdf}
\caption{Cosmos3 Edge: forecast and execution of the same 32-action chunk (episode RWS-E3-S1-C01-B-D, request~1, packet Aef9bebaab690; instruction ``Put the rubiks cube behind the bowl''). Top left: the left exterior camera's render at tick~32 ($t=2.133$\,s), the request input before downscaling to the policy's $320\times180$ view. The dashed box marks the displayed window, and objects are numbered as in the labelers' legend. Top right: the original independent VLM labels, assigned without the instruction or the execution; the two labelers disagreed on the final relation. Bottom: the same $160\times90$-pixel window of that view in two rows. The predicted row shows generated frame $k$. The executed row shows the simulator frame after $k$ of the 32 executed actions (tick $32+k$). Columns are $k=0,8,16,24,32$, spanning $t=2.133$--$4.267$\,s. In both rows the gripper reaches the cube and the cube stays beside the banana. Neither row shows the cube approaching the bowl. Columns follow the nominal 15\,Hz frame-to-tick mapping of the model and export code. It is not established that the generated motion keeps the executed pace. Frame~0 is the model's reconstruction of its input. The example was fixed before its media were viewed (rule: lexicographically first primary-window episode per model).}
\label{fig:forecast-example-edge}
\end{figure}
```

## Figure: FLUX 3 Action example

```latex
\begin{figure}[t]
\centering
\includegraphics[width=\linewidth]{rev_forecast_example_flux.pdf}
\caption{FLUX 3 Action: forecast and execution of the same 32-action chunk (episode RWS-F3-S1-C01-B-D, request~1, packet A5ee6df16bd49). The instruction and starting state match Figure~\ref{fig:forecast-example-edge}, and the layout is the same. The generated frames blur progressively. By $k=16$ the arm appears as a ghosted smear over the cube, while the banana and bowl remain recognizable. In the execution the gripper reaches the cube and the cube stays beside the banana. Neither row shows the cube approaching the bowl. The labelers disagreed on the relation object: one named the cube itself. FLUX decodes all generated frames jointly with a non-causal decoder, so even frame~0 depends on the predicted content. The pace and selection caveats of Figure~\ref{fig:forecast-example-edge} apply.}
\label{fig:forecast-example-flux}
\end{figure}
```

## Figure: original packet, Cosmos3 Edge

```latex
\begin{figure}[t]
\centering
\includegraphics[width=\linewidth]{rev_forecast_packet_edge.pdf}
\caption{Original annotation packet of the Cosmos3 Edge forecast in Figure~\ref{fig:forecast-example-edge}. Top: \texttt{legend.png}, as given to the VLM labelers. It shows the episode's first observation from both exterior cameras, with numbered object circles and direction arrows. Each number is drawn above and to the right of its circle. As a result, the arrow labels cover numbers 1 and 3 in the left view, and the cube's 3 falls on the banana's circle in the right view. Bottom: \texttt{contact\_sheet.png}, the human-review summary of every fourth generated frame (wrist view above the two exterior views). The labelers saw eight frames of the forecast video instead. The packet contains predictions only and is not paired with the execution.}
\label{fig:forecast-packet-edge}
\end{figure}
```

## Figure: original packet, FLUX 3 Action

```latex
\begin{figure}[t]
\centering
\includegraphics[width=\linewidth]{rev_forecast_packet_flux.pdf}
\caption{Original annotation packet of the FLUX 3 Action forecast in Figure~\ref{fig:forecast-example-flux}, laid out as in Figure~\ref{fig:forecast-packet-edge}. The legend is byte-identical to that of the Cosmos3 Edge packet; both episodes start from the same restored state. The packet contains predictions only and is not paired with the execution.}
\label{fig:forecast-packet-flux}
\end{figure}
```

## Optional body sentence

This would follow the sentence in `app:forecasts` (currently L518 of `revision_esmaeil.tex`) that ends "…should not be interpreted as a fully validated frame-by-frame forecast accuracy benchmark." That paragraph also says the temporal and camera correspondence documentation "remains to be attached". This work attaches it for two examples only, so for the other packets the statement still holds.

> For the two examples in Figures~\ref{fig:forecast-example-edge} and~\ref{fig:forecast-example-flux}, chosen by a fixed rule before their media were viewed, we checked the records and the model and export code. Each forecast comes from the same request as the executed chunk. Generated frame $k$ corresponds to the execution after $k$ actions, and the displayed window is the same exterior camera in both rows. Whether the generated motion proceeds at the executed pace remains unverified.

## What the figures do not establish

Paste these where a caption needs more detail.

- **Pace.** The pace of the generated motion is not established. A supporting diagnostic finds, for each generated frame, the most similar executed frame. In the left camera that best match plateaus at executed offsets 14–19 for k ≥ 20 in both models. The result is inconclusive: prediction errors confound it.
- **Frame 0.** Generated frame 0 is a decoded reconstruction, not the input. For FLUX it also depends on the predicted latents (non-causal decoder).
- **Executed frames.** They show what the simulator rendered after the controller tracked the commanded actions.
- **Cosmos3 Edge decoding.** It decodes 528 of the 540 composite rows. The displayed window lies inside the decoded rows.
- **Scope.** Only these two packets were verified.
