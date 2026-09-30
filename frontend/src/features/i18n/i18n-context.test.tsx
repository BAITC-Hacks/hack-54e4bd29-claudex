import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, expect, it } from "vitest";

import { LanguageProvider, LanguageSwitch } from "./i18n-context";

function DynamicLabel() {
  const [label, setLabel] = useState("Обзор");
  return <><LanguageSwitch /><button aria-label={label} onClick={() => setLabel("Сигналы")}>Update</button></>;
}

beforeEach(() => window.localStorage.clear());

it("translates an accessible label changed after selecting Kazakh", async () => {
  render(<LanguageProvider><DynamicLabel /></LanguageProvider>);
  fireEvent.click(screen.getByRole("button", { name: "Қаз" }));
  fireEvent.click(screen.getByText("Update"));

  await waitFor(() => expect(screen.getByText("Update")).toHaveAttribute("aria-label", "Сигналдар"));
});

it("localizes the forecast horizon unit inside a longer phrase", async () => {
  render(<LanguageProvider><LanguageSwitch /><p>Горизонт: 7 дней · период: октябрь</p></LanguageProvider>);

  fireEvent.click(screen.getByRole("button", { name: "Қаз" }));
  await waitFor(() => expect(screen.getByText("Көкжиек: 7 күн · кезең: октябрь")).toBeInTheDocument());
});

it("restores the original Russian CTA when two phrases share one translation", async () => {
  render(<LanguageProvider><LanguageSwitch /><p>Узнать больше</p></LanguageProvider>);

  fireEvent.click(screen.getByRole("button", { name: "Қаз" }));
  await waitFor(() => expect(screen.getByText("Толығырақ")).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: "Рус" }));
  await waitFor(() => expect(screen.getByText("Узнать больше")).toBeInTheDocument());
});

it("translates current situation-center context without hiding synthetic provenance", async () => {
  render(<LanguageProvider><LanguageSwitch /><p>Исторические агрегаты направлений, ожидания и отказов за выбранный период.</p><span>Синтетические данные</span></LanguageProvider>);

  fireEvent.click(screen.getByRole("button", { name: "Қаз" }));
  await waitFor(() => expect(screen.getByText("Таңдалған кезеңдегі жолдамалар, күту және бас тартулардың тарихи жиынтықтары.")).toBeInTheDocument());
  expect(screen.getByText("Синтетикалық деректер")).toBeInTheDocument();
});
