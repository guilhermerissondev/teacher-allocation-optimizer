import { describe, expect, it } from "vitest";
import {
  count,
  decimal,
  hours,
  megabytes,
  natural,
  percent,
  seconds,
  signedHours,
  signedNatural,
  signedPoints,
} from "./numberFormat";

describe("numberFormat", () => {
  it("usa vírgula decimal e ponto de milhar, como o report semanal", () => {
    expect(percent(64.23, 2)).toBe("64,23%");
    expect(hours(3988)).toBe("3.988h");
    expect(count(1208)).toBe("1.208");
  });

  it("fixa as casas para que a coluna de percentuais alinhe", () => {
    expect(percent(100)).toBe("100,0%");
    expect(percent(96.14)).toBe("96,1%");
    expect(decimal(7, 2)).toBe("7,00");
  });

  it("arredonda o percentual para a casa pedida", () => {
    expect(percent(96.15)).toBe("96,2%");
    expect(percent(0)).toBe("0,0%");
  });

  it("marca o sinal só quando a variação é positiva", () => {
    expect(signedHours(692)).toBe("+692h");
    expect(signedHours(-692)).toBe("-692h");
    expect(signedHours(0)).toBe("0h");
    expect(signedPoints(1.5)).toBe("+1,5 pp");
  });

  it("deixa as casas livres nos deltas, que vêm inteiros ou fracionários", () => {
    expect(natural(12)).toBe("12");
    expect(natural(1.5)).toBe("1,5");
    expect(signedNatural(3, " ofertas")).toBe("+3 ofertas");
  });

  it("formata tempo do motor e tamanho de arquivo", () => {
    expect(seconds(1.25)).toBe("1,3s");
    expect(megabytes(1024 * 1024 * 2.5)).toBe("2,50 MB");
  });
});
