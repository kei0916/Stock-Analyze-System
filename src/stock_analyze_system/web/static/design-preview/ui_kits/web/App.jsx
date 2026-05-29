// Top-level shell with simple hash-based routing.

const App = () => {
  const [route, setRoute] = React.useState(() => (window.location.hash || "#dashboard").slice(1));
  React.useEffect(() => {
    const onHash = () => setRoute((window.location.hash || "#dashboard").slice(1));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const navigate = (r) => { window.location.hash = "#" + r; };

  if (route === "login") return <Login/>;

  let body, breadcrumbs;
  if (route.startsWith("stocks/")) {
    const id = route.split("/")[1] || "US_AAPL";
    const c = MOCK_COMPANIES.find(x => x.id === id);
    body = <StockDetail companyId={id} navigate={navigate}/>;
    breadcrumbs = ["銘柄", c?.name_ja || id];
  } else if (route === "screening") {
    body = <Screening navigate={navigate}/>; breadcrumbs = ["スクリーニング"];
  } else if (route === "watchlists") {
    body = <Watchlists navigate={navigate}/>; breadcrumbs = ["ウォッチリスト"];
  } else if (route === "stocks") {
    body = <Screening navigate={navigate}/>; breadcrumbs = ["銘柄"];
  } else {
    body = <Dashboard navigate={navigate}/>; breadcrumbs = ["ダッシュボード"];
  }
  return <Layout route={route} navigate={navigate} breadcrumbs={breadcrumbs}>{body}</Layout>;
};

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App/>);
