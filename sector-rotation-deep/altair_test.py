import pandas as pd
import altair as alt

data = pd.DataFrame({
    "sector": ["A", "B", "C"],
    "avg_percent_change": [1.5, 3.2, 0.5],
    "percent_change_fmt": ["+1.5%", "+3.2%", "+0.5%"]
})

winners = data.sort_values("avg_percent_change", ascending=False)
domain_w = winners["sector"].tolist()

base_w = alt.Chart(winners).encode(
    y=alt.Y("sector:N", sort=domain_w, axis=alt.Axis(title=None, labels=False, ticks=False, domain=False))
)

bars_w = base_w.mark_bar(color="#FF4B4B", cornerRadiusEnd=4, size=24).encode(
    x=alt.X("avg_percent_change:Q", axis=alt.Axis(title=None, labels=False, ticks=False, grid=False, domain=False))
)

text_w = base_w.mark_text(align="left", dx=4, color="white", fontWeight="bold").encode(
    x=alt.X("avg_percent_change:Q"),
    text=alt.Text("percent_change_fmt:N")
)

label_w = base_w.mark_text(align="left", dx=4, color="white").encode(
    x=alt.datum(0),
    text=alt.Text("sector:N")
)

fig_w = alt.layer(bars_w, text_w, label_w).configure_view(strokeWidth=0).properties(height=200)

print(fig_w.to_json())
