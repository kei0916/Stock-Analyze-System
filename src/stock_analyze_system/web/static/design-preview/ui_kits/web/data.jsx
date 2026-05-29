// Mock data for the prototype.
const MOCK_COMPANIES = [
  { id: "US_AAPL", ticker: "AAPL", name: "Apple Inc.", name_ja: "アップル", market: "NASDAQ", sector: "Technology", standard: "US-GAAP", price: 178.32, per: 28.45, pbr: 45.62, psr: 7.41, evEbitda: 21.18, fcfYield: 0.0342, roe: 1.562, change1y: 0.241, marketCap: 2_780_000_000_000 },
  { id: "US_MSFT", ticker: "MSFT", name: "Microsoft Corp.", name_ja: "マイクロソフト", market: "NASDAQ", sector: "Technology", standard: "US-GAAP", price: 415.10, per: 34.18, pbr: 12.84, psr: 12.6, evEbitda: 23.5, fcfYield: 0.0285, roe: 0.385, change1y: 0.187, marketCap: 3_080_000_000_000 },
  { id: "JP_7203", ticker: "7203", name: "Toyota Motor Corp.", name_ja: "トヨタ自動車", market: "TSE",   sector: "Automobiles", standard: "JP-GAAP", price: 2845, per: 10.21, pbr: 1.18, psr: 0.85, evEbitda: 8.4, fcfYield: 0.0612, roe: 0.116, change1y: -0.042, marketCap: 39_500_000_000_000 },
  { id: "US_BRK-B", ticker: "BRK-B", name: "Berkshire Hathaway B", name_ja: "バークシャー・ハサウェイ", market: "NYSE", sector: "Financials", standard: "US-GAAP", price: 418.55, per: 9.87, pbr: 1.55, psr: 2.1, evEbitda: 6.8, fcfYield: 0.058, roe: 0.174, change1y: 0.123, marketCap: 901_000_000_000 },
  { id: "JP_6758", ticker: "6758", name: "Sony Group", name_ja: "ソニーグループ", market: "TSE", sector: "Consumer Electronics", standard: "JP-GAAP", price: 3210, per: 16.42, pbr: 2.04, psr: 1.4, evEbitda: 9.1, fcfYield: 0.0455, roe: 0.121, change1y: -0.018, marketCap: 19_400_000_000_000 },
  { id: "US_NVDA", ticker: "NVDA", name: "NVIDIA Corp.", name_ja: "エヌビディア", market: "NASDAQ", sector: "Technology", standard: "US-GAAP", price: 894.20, per: 65.30, pbr: 48.10, psr: 22.3, evEbitda: 49.8, fcfYield: 0.0125, roe: 0.951, change1y: 1.428, marketCap: 2_200_000_000_000 },
  { id: "US_GOOGL", ticker: "GOOGL", name: "Alphabet Inc.", name_ja: "アルファベット", market: "NASDAQ", sector: "Technology", standard: "US-GAAP", price: 162.40, per: 24.85, pbr: 6.42, psr: 5.8, evEbitda: 16.2, fcfYield: 0.0412, roe: 0.272, change1y: 0.281, marketCap: 2_010_000_000_000 },
  { id: "JP_9984", ticker: "9984", name: "SoftBank Group", name_ja: "ソフトバンクグループ", market: "TSE", sector: "Telecom", standard: "JP-GAAP", price: 8420, per: 18.20, pbr: 1.62, psr: 1.1, evEbitda: 11.4, fcfYield: 0.038, roe: 0.092, change1y: 0.341, marketCap: 12_300_000_000_000 },
  { id: "US_AMZN", ticker: "AMZN", name: "Amazon.com", name_ja: "アマゾン", market: "NASDAQ", sector: "Consumer Discretionary", standard: "US-GAAP", price: 184.50, per: 42.15, pbr: 7.85, psr: 3.2, evEbitda: 18.4, fcfYield: 0.022, roe: 0.184, change1y: 0.295, marketCap: 1_920_000_000_000 },
  { id: "US_META", ticker: "META", name: "Meta Platforms", name_ja: "メタ", market: "NASDAQ", sector: "Technology", standard: "US-GAAP", price: 510.20, per: 26.10, pbr: 8.45, psr: 9.4, evEbitda: 14.8, fcfYield: 0.038, roe: 0.341, change1y: 0.452, marketCap: 1_310_000_000_000 },
  { id: "US_TSLA", ticker: "TSLA", name: "Tesla Inc.", name_ja: "テスラ", market: "NASDAQ", sector: "Automobiles", standard: "US-GAAP", price: 178.10, per: 58.40, pbr: 11.20, psr: 6.8, evEbitda: 32.5, fcfYield: 0.018, roe: 0.215, change1y: -0.124, marketCap: 568_000_000_000 },
  { id: "US_JPM", ticker: "JPM", name: "JPMorgan Chase", name_ja: "JPモルガン・チェース", market: "NYSE", sector: "Financials", standard: "US-GAAP", price: 198.40, per: 11.85, pbr: 1.82, psr: 3.4, evEbitda: 9.2, fcfYield: 0.085, roe: 0.158, change1y: 0.341, marketCap: 580_000_000_000 },
  { id: "US_V", ticker: "V", name: "Visa Inc.", name_ja: "ビザ", market: "NYSE", sector: "Financials", standard: "US-GAAP", price: 271.30, per: 30.20, pbr: 13.40, psr: 16.8, evEbitda: 22.1, fcfYield: 0.034, roe: 0.451, change1y: 0.158, marketCap: 545_000_000_000 },
  { id: "US_JNJ", ticker: "JNJ", name: "Johnson & Johnson", name_ja: "ジョンソン・エンド・ジョンソン", market: "NYSE", sector: "Healthcare", standard: "US-GAAP", price: 152.10, per: 14.85, pbr: 5.12, psr: 4.2, evEbitda: 11.5, fcfYield: 0.054, roe: 0.241, change1y: -0.052, marketCap: 366_000_000_000 },
  { id: "US_KO", ticker: "KO", name: "Coca-Cola", name_ja: "コカ・コーラ", market: "NYSE", sector: "Consumer Staples", standard: "US-GAAP", price: 64.20, per: 25.40, pbr: 11.85, psr: 6.2, evEbitda: 19.4, fcfYield: 0.038, roe: 0.421, change1y: 0.082, marketCap: 277_000_000_000 },
  { id: "US_PFE", ticker: "PFE", name: "Pfizer Inc.", name_ja: "ファイザー", market: "NYSE", sector: "Healthcare", standard: "US-GAAP", price: 28.40, per: 18.90, pbr: 1.85, psr: 2.4, evEbitda: 12.8, fcfYield: 0.062, roe: 0.085, change1y: -0.124, marketCap: 161_000_000_000 },
  { id: "JP_8306", ticker: "8306", name: "Mitsubishi UFJ", name_ja: "三菱UFJフィナンシャル・グループ", market: "TSE", sector: "Financials", standard: "JP-GAAP", price: 1684, per: 12.40, pbr: 0.92, psr: 1.8, evEbitda: 8.5, fcfYield: 0.075, roe: 0.082, change1y: 0.281, marketCap: 21_400_000_000_000 },
  { id: "JP_6861", ticker: "6861", name: "Keyence Corp.", name_ja: "キーエンス", market: "TSE", sector: "Industrials", standard: "JP-GAAP", price: 62420, per: 38.50, pbr: 5.82, psr: 12.4, evEbitda: 26.4, fcfYield: 0.022, roe: 0.158, change1y: 0.045, marketCap: 15_200_000_000_000 },
  { id: "JP_9433", ticker: "9433", name: "KDDI Corp.", name_ja: "KDDI", market: "TSE", sector: "Telecom", standard: "JP-GAAP", price: 4521, per: 13.20, pbr: 1.78, psr: 1.6, evEbitda: 6.8, fcfYield: 0.064, roe: 0.135, change1y: 0.094, marketCap: 9_800_000_000_000 },
  { id: "JP_7974", ticker: "7974", name: "Nintendo Co.", name_ja: "任天堂", market: "TSE", sector: "Consumer Discretionary", standard: "JP-GAAP", price: 7820, per: 21.40, pbr: 3.24, psr: 4.8, evEbitda: 13.2, fcfYield: 0.045, roe: 0.158, change1y: 0.124, marketCap: 9_400_000_000_000 },
];

// Annual financials — past 15 years (FY2010 → FY2024). Apple-like figures.
const APPLE_FINANCIALS_ANNUAL = [
  { fy: "2010", revenue: 65225,  opIncome: 18385,  netIncome: 14013,  ebitda: 19412,  fcf: 16590,  eps: 0.54 },
  { fy: "2011", revenue: 108249, opIncome: 33790,  netIncome: 25922,  ebitda: 35604,  fcf: 33269,  eps: 1.00 },
  { fy: "2012", revenue: 156508, opIncome: 55241,  netIncome: 41733,  ebitda: 58518,  fcf: 41454,  eps: 1.59 },
  { fy: "2013", revenue: 170910, opIncome: 48999,  netIncome: 37037,  ebitda: 55756,  fcf: 44590,  eps: 1.43 },
  { fy: "2014", revenue: 182795, opIncome: 52503,  netIncome: 39510,  ebitda: 60449,  fcf: 49900,  eps: 1.62 },
  { fy: "2015", revenue: 233715, opIncome: 71230,  netIncome: 53394,  ebitda: 82487,  fcf: 69778,  eps: 2.31 },
  { fy: "2016", revenue: 215639, opIncome: 60024,  netIncome: 45687,  ebitda: 73333,  fcf: 52276,  eps: 2.08 },
  { fy: "2017", revenue: 229234, opIncome: 61344,  netIncome: 48351,  ebitda: 71501,  fcf: 50803,  eps: 2.30 },
  { fy: "2018", revenue: 265595, opIncome: 70898,  netIncome: 59531,  ebitda: 81801,  fcf: 64121,  eps: 2.98 },
  { fy: "2019", revenue: 260174, opIncome: 63930,  netIncome: 55256,  ebitda: 76477,  fcf: 58896,  eps: 2.97 },
  { fy: "2020", revenue: 274515, opIncome: 66288,  netIncome: 57411,  ebitda: 81020,  fcf: 73365,  eps: 3.28 },
  { fy: "2021", revenue: 365817, opIncome: 108949, netIncome: 94680,  ebitda: 123136, fcf: 92953,  eps: 5.61 },
  { fy: "2022", revenue: 394328, opIncome: 119437, netIncome: 99803,  ebitda: 130541, fcf: 111443, eps: 6.11 },
  { fy: "2023", revenue: 383285, opIncome: 114301, netIncome: 96995,  ebitda: 129198, fcf: 99584,  eps: 6.13 },
  { fy: "2024", revenue: 391035, opIncome: 123216, netIncome: 93736,  ebitda: 134661, fcf: 108807, eps: 6.08 },
];

const APPLE_FINANCIALS_QUARTERLY = [
  { fy: "Q1'23", revenue: 117154, opIncome: 36016, netIncome: 29998, ebitda: 40268, fcf: 30217, eps: 1.88 },
  { fy: "Q2'23", revenue: 94836,  opIncome: 28318, netIncome: 24160, ebitda: 32144, fcf: 26349, eps: 1.52 },
  { fy: "Q3'23", revenue: 81797,  opIncome: 22998, netIncome: 19881, ebitda: 26447, fcf: 24181, eps: 1.26 },
  { fy: "Q4'23", revenue: 89498,  opIncome: 26969, netIncome: 22956, ebitda: 30339, fcf: 18837, eps: 1.46 },
  { fy: "Q1'24", revenue: 119575, opIncome: 40373, netIncome: 33916, ebitda: 44561, fcf: 37533, eps: 2.18 },
  { fy: "Q2'24", revenue: 90753,  opIncome: 27900, netIncome: 23636, ebitda: 31816, fcf: 22791, eps: 1.53 },
  { fy: "Q3'24", revenue: 85777,  opIncome: 25352, netIncome: 21448, ebitda: 28954, fcf: 26684, eps: 1.40 },
  { fy: "Q4'24", revenue: 94930,  opIncome: 29591, netIncome: 14736, ebitda: 29330, fcf: 21799, eps: 0.97 },
];

const APPLE_PER_SERIES = [
  18.4,19.2,20.1,21.5,22.8,24.1,25.6,24.9,23.7,25.2,26.8,28.4,
  29.1,28.7,27.3,26.1,24.8,23.5,25.6,27.4,28.9,30.1,29.5,28.2,
  27.8,29.4,31.2,30.8,32.1,33.5,32.4,30.9,29.6,28.4,27.5,28.5,
];

Object.assign(window, { MOCK_COMPANIES, APPLE_FINANCIALS_ANNUAL, APPLE_FINANCIALS_QUARTERLY, APPLE_PER_SERIES });
