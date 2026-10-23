// Pieces shared by the light (box, recipe) views.

import { h, icon, logo } from "../dom.js";

export const COURSE = {
  main: { label: "Main", plural: "Mains", icon: "main", tile: ["#F3D9CF", "#8E3B22"] },
  side: { label: "Side", plural: "Sides", icon: "bowl", tile: ["#DCE3D6", "#173E32"] },
  soup: { label: "Soup", plural: "Soups", icon: "bowl", tile: ["#F6DFAE", "#6B4A0B"] },
  salad: { label: "Salad", plural: "Salads", icon: "leaf", tile: ["#DCE3D6", "#173E32"] },
  bread: { label: "Bread", plural: "Bread", icon: "bread", tile: ["#F6DFAE", "#6B4A0B"] },
  sauce: { label: "Sauce", plural: "Sauces", icon: "jar", tile: ["#EADFC6", "#3F453D"] },
  appetizer: { label: "Appetizer", plural: "Appetizers", icon: "main", tile: ["#EADFC6", "#3F453D"] },
  dessert: { label: "Dessert", plural: "Desserts", icon: "cake", tile: ["#F3D9CF", "#8E3B22"] },
  drink: { label: "Drink", plural: "Drinks", icon: "glass", tile: ["#173E32", "#F7EEDB"] },
  breakfast: { label: "Breakfast", plural: "Breakfast", icon: "jar", tile: ["#EADFC6", "#3F453D"] },
  snack: { label: "Snack", plural: "Snacks", icon: "book", tile: ["#EADFC6", "#3F453D"] },
};

export function courseInfo(course) {
  return COURSE[course] || { label: "Recipe", plural: "Other", icon: "book", tile: ["#EADFC6", "#3F453D"] };
}

export function tile(course) {
  const c = courseInfo(course);
  return h("div", { class: "tile", style: { background: c.tile[0], color: c.tile[1] } },
    icon(c.icon, 26, { stroke: 1.8 }));
}

export function topbar(...right) {
  return h("header", { class: "topbar" },
    h("div", { class: "wrap" },
      h("a", { class: "brand", href: "/" }, logo(34), h("span", {}, "Dogear")),
      h("div", { class: "spacer" }),
      ...right));
}

export function stars(n, size = 14) {
  return h("span", { class: "stars-sm", "aria-label": `${n} of 5 stars`, role: "img" },
    Array.from({ length: n }, () => icon("star", size, { filled: true, stroke: 1.2 })));
}

export function setTitle(text) {
  document.title = text ? `${text} · Dogear` : "Dogear";
}
