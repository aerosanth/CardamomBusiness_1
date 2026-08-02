import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import calendar
import os

# Connect to databases
conn_price = sqlite3.connect('data/cardamom_data.db')
df_price = pd.read_sql_query('SELECT date_of_auction as date, avg_price FROM cardamom_prices', conn_price)
conn_price.close()

conn_rain = sqlite3.connect('data/ranfill_data.db')
df_rain = pd.read_sql_query("SELECT date, rainfall_bilinear_mm as rainfall FROM rainfall_data WHERE location='Pooparai'", conn_rain)
conn_rain.close()

# Preprocess Dates
df_price['date'] = pd.to_datetime(df_price['date'])
df_rain['date'] = pd.to_datetime(df_rain['date'])

df_price['Year'] = df_price['date'].dt.year
df_price['Month'] = df_price['date'].dt.month
df_rain['Year'] = df_rain['date'].dt.year
df_rain['Month'] = df_rain['date'].dt.month

# Aggregate
price_monthly = df_price.groupby(['Year', 'Month'])['avg_price'].mean().reset_index()
rain_monthly = df_rain.groupby(['Year', 'Month'])['rainfall'].sum().reset_index()

price_pivot = price_monthly.pivot(index='Year', columns='Month', values='avg_price')
rain_pivot = rain_monthly.pivot(index='Year', columns='Month', values='rainfall')

months = [calendar.month_abbr[i] for i in range(1, 13)]
price_pivot.columns = [calendar.month_abbr[i] for i in price_pivot.columns]
rain_pivot.columns = [calendar.month_abbr[i] for i in rain_pivot.columns]

# Ensure artifacts directory exists
os.makedirs('/home/v252lin/.gemini/antigravity/brain/a57d7925-e4e2-4226-897e-a2b196f8fa63/artifacts', exist_ok=True)

# 1. Heatmaps
fig, axes = plt.subplots(1, 2, figsize=(18, 6))

axes[0].imshow(price_pivot.values, cmap='YlGnBu', aspect='auto')
axes[0].set_title('Avg Cardamom Price Heatmap (Year vs Month)')
axes[0].set_yticks(range(len(price_pivot.index)))
axes[0].set_yticklabels(price_pivot.index)
axes[0].set_xticks(range(len(price_pivot.columns)))
axes[0].set_xticklabels(price_pivot.columns)

rain_pivot_recent = rain_pivot.loc[price_pivot.index.min():]
axes[1].imshow(rain_pivot_recent.values, cmap='Blues', aspect='auto')
axes[1].set_title('Total Rainfall (mm) Heatmap - Pooparai')
axes[1].set_yticks(range(len(rain_pivot_recent.index)))
axes[1].set_yticklabels(rain_pivot_recent.index)
axes[1].set_xticks(range(len(rain_pivot_recent.columns)))
axes[1].set_xticklabels(rain_pivot_recent.columns)

plt.tight_layout()
plt.savefig('/home/v252lin/.gemini/antigravity/brain/a57d7925-e4e2-4226-897e-a2b196f8fa63/artifacts/heatmaps.png')
plt.close()

# 2. Seasonality Line Chart
fig, axes = plt.subplots(2, 1, figsize=(12, 10), sharex=True)

for year in price_monthly['Year'].unique():
    subset = price_monthly[price_monthly['Year'] == year]
    axes[0].plot(subset['Month'], subset['avg_price'], marker='o', label=str(year) if year % 2 == 0 else "")

axes[0].set_title('Cardamom Price Seasonality (Yearly Lines)')
axes[0].set_ylabel('Average Price (Rs)')
axes[0].grid(True, alpha=0.3)
axes[0].legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize='small')

rain_monthly_recent = rain_monthly[rain_monthly['Year'] >= price_monthly['Year'].min()]
for year in rain_monthly_recent['Year'].unique():
    subset = rain_monthly_recent[rain_monthly_recent['Year'] == year]
    axes[1].plot(subset['Month'], subset['rainfall'], marker='o')

axes[1].set_title('Rainfall Seasonality (Yearly Lines)')
axes[1].set_ylabel('Total Rainfall (mm)')
axes[1].set_xticks(range(1, 13))
axes[1].set_xticklabels(months)
axes[1].grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('/home/v252lin/.gemini/antigravity/brain/a57d7925-e4e2-4226-897e-a2b196f8fa63/artifacts/seasonality.png')
plt.close()

print("Graphs generated!")
