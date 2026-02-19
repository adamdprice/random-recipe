(function () {
  "use strict";

  const homeView = document.getElementById("home-view");
  const recipeView = document.getElementById("recipe-view");
  const pickRecipeBtn = document.getElementById("pick-recipe-btn");
  const backBtn = document.getElementById("back-btn");
  const randomRecipeBtn = document.getElementById("random-recipe-btn");
  const recipeNameEl = document.getElementById("recipe-name");
  const recipeImageEl = document.getElementById("recipe-image");
  const highlightsGrid = document.getElementById("highlights-grid");
  const ingredientsList = document.getElementById("ingredients-list");
  const tipsList = document.getElementById("tips-list");
  const stepText = document.getElementById("step-text");
  const stepCounter = document.getElementById("step-counter");
  const prevStepBtn = document.getElementById("prev-step-btn");
  const nextStepBtn = document.getElementById("next-step-btn");

  let currentRecipe = null;
  let currentStepIndex = 0;

  function pickRandomRecipe() {
    if (!RECIPES || RECIPES.length === 0) return null;
    const index = Math.floor(Math.random() * RECIPES.length);
    return RECIPES[index];
  }

  function showView(view) {
    homeView.classList.remove("active");
    homeView.hidden = view === "recipe";
    recipeView.classList.remove("active");
    recipeView.hidden = view === "home";
    if (view === "home") {
      homeView.classList.add("active");
    } else {
      recipeView.classList.add("active");
    }
  }

  function renderHighlights(recipe) {
    const items = [
      {
        icon: "🌾",
        label: "Gluten free",
        value: recipe.gluten_free ? "Yes" : "No"
      },
      {
        icon: "🥚",
        label: "Egg free",
        value: recipe.egg_free ? "Yes" : "No"
      },
      {
        icon: "🍽️",
        label: "Servings",
        value: String(recipe.servings)
      },
      {
        icon: "⏱️",
        label: "Prep",
        value: recipe.prep_time_minutes + " min"
      },
      {
        icon: "🔥",
        label: "Cook",
        value: recipe.cook_time_minutes + " min"
      },
      {
        icon: "📋",
        label: "Total",
        value: recipe.total_time_minutes + " min"
      },
      {
        icon: "⭐",
        label: "Kid rating",
        value: recipe.kid_rating + " / 5"
      }
    ];

    highlightsGrid.innerHTML = items
      .map(
        (item) =>
          `<div class="highlight-chip">
            <span class="icon">${item.icon}</span>
            <span><span class="label">${item.label}</span> <span class="value">${item.value}</span></span>
          </div>`
      )
      .join("");
  }

  function renderIngredients(recipe) {
    ingredientsList.innerHTML = recipe.ingredients
      .map((i) => `<li>${escapeHtml(i)}</li>`)
      .join("");
  }

  function renderTips(recipe) {
    tipsList.innerHTML = recipe.tips
      .map((t) => `<li>${escapeHtml(t)}</li>`)
      .join("");
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function updateStepUI() {
    if (!currentRecipe) return;
    const steps = currentRecipe.instructions;
    const total = steps.length;
    const index = currentStepIndex;
    const step = steps[index];

    stepText.textContent = step || "";
    stepCounter.textContent = `Step ${index + 1} of ${total}`;

    prevStepBtn.disabled = index <= 0;
    nextStepBtn.disabled = index >= total - 1;
    nextStepBtn.textContent = index >= total - 1 ? "Done" : "Next";
  }

  function showRecipe(recipe) {
    currentRecipe = recipe;
    currentStepIndex = 0;

    recipeNameEl.textContent = recipe.name;
    recipeImageEl.src = recipe.image || "";
    recipeImageEl.alt = recipe.name;

    renderHighlights(recipe);
    renderIngredients(recipe);
    renderTips(recipe);
    updateStepUI();

    showView("recipe");
  }

  pickRecipeBtn.addEventListener("click", function () {
    const recipe = pickRandomRecipe();
    if (recipe) showRecipe(recipe);
  });

  backBtn.addEventListener("click", function () {
    showView("home");
  });

  randomRecipeBtn.addEventListener("click", function () {
    const recipe = pickRandomRecipe();
    if (recipe) showRecipe(recipe);
  });

  prevStepBtn.addEventListener("click", function () {
    if (currentStepIndex <= 0) return;
    currentStepIndex -= 1;
    updateStepUI();
  });

  nextStepBtn.addEventListener("click", function () {
    if (currentStepIndex >= currentRecipe.instructions.length - 1) return;
    currentStepIndex += 1;
    updateStepUI();
  });
})();
