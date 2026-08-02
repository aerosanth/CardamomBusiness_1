import sqlite3
import pandas as pd
import json

conn_price = sqlite3.connect('data/cardamom_data.db')
df_price = pd.read_sql_query('SELECT date_of_auction as date, avg_price FROM cardamom_prices', conn_price)
conn_price.close()

conn_rain = sqlite3.connect('data/ranfill_data.db')
df_rain = pd.read_sql_query("SELECT date, rainfall_bilinear_mm as rainfall FROM rainfall_data WHERE location='Pooparai'", conn_rain)
conn_rain.close()

df_price['date'] = pd.to_datetime(df_price['date'])
df_rain['date'] = pd.to_datetime(df_rain['date'])

df_price['Year'] = df_price['date'].dt.year
df_price['Month'] = df_price['date'].dt.month
df_rain['Year'] = df_rain['date'].dt.year
df_rain['Month'] = df_rain['date'].dt.month

price_monthly = df_price.groupby(['Year', 'Month'])['avg_price'].mean().reset_index()
rain_monthly = df_rain.groupby(['Year', 'Month'])['rainfall'].sum().reset_index()

price_agg = price_monthly.groupby('Month')['avg_price'].mean().reset_index()
rain_agg = rain_monthly.groupby('Month')['rainfall'].mean().reset_index()

res = {
    "price_overall": price_agg.to_dict('records'),
    "rain_overall": rain_agg.to_dict('records'),
}
print(json.dumps(res, indent=2))
