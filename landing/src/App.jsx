import { Header } from "./components/Header.jsx";
import { Hero } from "./components/Hero.jsx";
import { HowItWorks } from "./components/HowItWorks.jsx";
import { AttacksDemo } from "./components/AttacksDemo.jsx";
import { TechStack } from "./components/TechStack.jsx";
import { Team, Footer } from "./components/Team.jsx";

export function App() {
  return (
    <div class="page">
      <div class="page__grid-bg" aria-hidden="true" />
      <Header />
      <main>
        <Hero />
        <HowItWorks />
        <AttacksDemo />
        <TechStack />
        <Team />
      </main>
      <Footer />
    </div>
  );
}
