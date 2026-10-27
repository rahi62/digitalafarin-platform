import { describe, expect, it } from "vitest";
import { routeParam } from "./params.js";

describe("routeParam", () => {
  it("returns a scalar route parameter unchanged", () => {
    expect(routeParam("project-1")).toBe("project-1");
  });

  it("uses the first value when Express types a route parameter as an array", () => {
    expect(routeParam(["project-1", "project-2"])).toBe("project-1");
  });

  it("returns an empty string for an empty route parameter array", () => {
    expect(routeParam([])).toBe("");
  });
});
