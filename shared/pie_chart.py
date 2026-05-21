import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def save_pie(country_sum: pd.DataFrame, png_path: str, top_n: int = 12):
    cs = country_sum.copy()
    cs = cs[cs["Country"] != "Unknown"]
    if len(cs) == 0:
        return

    if len(cs) > top_n:
        top = cs.head(top_n).copy()
        other = cs.iloc[top_n:]["Country_Count_Sum"].sum()
        top = pd.concat([top, pd.DataFrame([{"Country": "Other", "Country_Count_Sum": other}])], ignore_index=True)
        cs_plot = top
    else:
        cs_plot = cs

    plt.figure(figsize=(9, 7))
    plt.pie(cs_plot["Country_Count_Sum"], labels=cs_plot["Country"], autopct="%1.1f%%")
    plt.title("News Count by Country")
    plt.tight_layout()
    plt.savefig(png_path, dpi=200)
    plt.close()
