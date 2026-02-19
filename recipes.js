// Recipe data with corresponding Unsplash images (free to use)
const RECIPES = [
  {
    id: 1,
    name: "Cheesy Chicken Quesadillas",
    image: "https://images.unsplash.com/photo-1618040996337-56904b7850b9?w=800&q=80",
    gluten_free: true,
    egg_free: true,
    servings: 4,
    prep_time_minutes: 10,
    cook_time_minutes: 10,
    total_time_minutes: 20,
    ingredients: [
      "Gluten-free tortillas",
      "Cooked shredded chicken",
      "Grated cheddar cheese",
      "Bell peppers (sliced)",
      "Salt",
      "Pepper",
      "Olive oil"
    ],
    instructions: [
      "Heat a pan on medium heat with a little olive oil.",
      "Lay one tortilla in the pan and sprinkle cheese on top.",
      "Add chicken and peppers, then add more cheese.",
      "Top with another tortilla and cook 2 to 3 minutes per side until golden.",
      "Slice into wedges and serve."
    ],
    kid_rating: 5,
    tips: [
      "Serve with salsa or sour cream.",
      "Swap chicken for ham or beans."
    ]
  },
  {
    id: 2,
    name: "Gluten-Free Mini Pizzas",
    image: "https://images.unsplash.com/photo-1513104890138-7c749659a591?w=800&q=80",
    gluten_free: true,
    egg_free: true,
    servings: 4,
    prep_time_minutes: 10,
    cook_time_minutes: 12,
    total_time_minutes: 22,
    ingredients: [
      "Gluten-free pizza bases or gluten-free bagels",
      "Tomato sauce",
      "Mozzarella cheese",
      "Pepperoni (optional)",
      "Sweetcorn",
      "Mushrooms",
      "Olive oil"
    ],
    instructions: [
      "Preheat oven to 200°C.",
      "Spread tomato sauce over each mini base.",
      "Add cheese and toppings.",
      "Bake for 10 to 12 minutes until bubbly.",
      "Cool slightly and serve."
    ],
    kid_rating: 5,
    tips: [
      "Let kids build their own toppings.",
      "Use dairy-free cheese if needed."
    ]
  },
  {
    id: 3,
    name: "Taco Stuffed Zucchini Boats",
    image: "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=800&q=80",
    gluten_free: true,
    egg_free: true,
    servings: 4,
    prep_time_minutes: 15,
    cook_time_minutes: 20,
    total_time_minutes: 35,
    ingredients: [
      "Zucchini (courgettes)",
      "Minced beef or turkey",
      "Taco seasoning (gluten-free)",
      "Salsa",
      "Grated cheese",
      "Olive oil",
      "Salt"
    ],
    instructions: [
      "Preheat oven to 200°C.",
      "Slice zucchinis in half and scoop out the middle.",
      "Cook mince in a pan with taco seasoning.",
      "Fill zucchini halves with cooked mince and top with salsa and cheese.",
      "Bake 15 to 20 minutes until tender."
    ],
    kid_rating: 4,
    tips: [
      "Serve with rice for a fuller meal.",
      "Swap mince for beans for veggie version."
    ]
  },
  {
    id: 4,
    name: "Gluten-Free Mac & Cheese",
    image: "https://images.unsplash.com/photo-1543339494-b4cd4f7ba686?w=800&q=80",
    gluten_free: true,
    egg_free: true,
    servings: 4,
    prep_time_minutes: 10,
    cook_time_minutes: 15,
    total_time_minutes: 25,
    ingredients: [
      "Gluten-free pasta",
      "Butter",
      "Milk (or dairy-free milk)",
      "Cheddar cheese",
      "Cornflour",
      "Salt",
      "Pepper"
    ],
    instructions: [
      "Cook gluten-free pasta according to packet instructions.",
      "In a pan, melt butter and stir in cornflour.",
      "Slowly whisk in milk until thickened.",
      "Stir in cheese until melted.",
      "Mix sauce with pasta and serve."
    ],
    kid_rating: 5,
    tips: [
      "Add cooked peas or sweetcorn for hidden veg.",
      "Top with gluten-free breadcrumbs for crunch."
    ]
  },
  {
    id: 5,
    name: "Crispy Baked Chicken Tenders",
    image: "https://images.unsplash.com/photo-1562967916-eb82221dfb92?w=800&q=80",
    gluten_free: true,
    egg_free: true,
    servings: 4,
    prep_time_minutes: 15,
    cook_time_minutes: 20,
    total_time_minutes: 35,
    ingredients: [
      "Chicken strips",
      "Gluten-free breadcrumbs",
      "Garlic powder",
      "Paprika",
      "Salt",
      "Olive oil"
    ],
    instructions: [
      "Preheat oven to 200°C.",
      "Mix breadcrumbs with garlic powder, paprika and salt.",
      "Coat chicken strips in olive oil then roll in breadcrumb mix.",
      "Place on baking tray and bake 18 to 20 minutes.",
      "Serve with ketchup or BBQ sauce."
    ],
    kid_rating: 5,
    tips: [
      "Use crushed gluten-free cornflakes for extra crunch.",
      "Works great in an air fryer too."
    ]
  },
  {
    id: 6,
    name: "Rainbow Fruit Parfaits",
    image: "https://images.unsplash.com/photo-1511690656952-34342bb7c2f2?w=800&q=80",
    gluten_free: true,
    egg_free: true,
    servings: 4,
    prep_time_minutes: 10,
    cook_time_minutes: 0,
    total_time_minutes: 10,
    ingredients: [
      "Strawberries",
      "Blueberries",
      "Banana",
      "Grapes",
      "Yogurt (or dairy-free yogurt)",
      "Gluten-free granola"
    ],
    instructions: [
      "Chop fruit into bite-size pieces.",
      "Layer yogurt, fruit and granola into cups.",
      "Repeat layers until cups are full.",
      "Serve immediately."
    ],
    kid_rating: 5,
    tips: [
      "Use honey or maple syrup if you want it sweeter.",
      "Great as a breakfast or snack."
    ]
  },
  {
    id: 7,
    name: "Veggie & Rice Nuggets",
    image: "https://images.unsplash.com/photo-1562967914-608f82629710?w=800&q=80",
    gluten_free: true,
    egg_free: true,
    servings: 4,
    prep_time_minutes: 15,
    cook_time_minutes: 20,
    total_time_minutes: 35,
    ingredients: [
      "Cooked rice",
      "Grated carrot",
      "Grated courgette",
      "Cheese (optional)",
      "Gluten-free breadcrumbs",
      "Salt",
      "Pepper",
      "Olive oil"
    ],
    instructions: [
      "Preheat oven to 200°C.",
      "Mix rice, grated veggies, cheese and seasoning in a bowl.",
      "Shape into nugget balls or patties.",
      "Roll in gluten-free breadcrumbs.",
      "Bake 18 to 20 minutes until golden."
    ],
    kid_rating: 4,
    tips: [
      "Serve with ketchup or sweet chilli sauce.",
      "Add cooked chicken for extra protein."
    ]
  },
  {
    id: 8,
    name: "BBQ Chicken & Potato Skewers",
    image: "https://images.unsplash.com/photo-1558030006-450675393462?w=800&q=80",
    gluten_free: true,
    egg_free: true,
    servings: 4,
    prep_time_minutes: 15,
    cook_time_minutes: 20,
    total_time_minutes: 35,
    ingredients: [
      "Chicken chunks",
      "Baby potatoes (parboiled)",
      "Bell peppers",
      "Gluten-free BBQ sauce",
      "Olive oil",
      "Salt"
    ],
    instructions: [
      "Preheat oven to 200°C or heat grill.",
      "Thread chicken, potatoes and peppers onto skewers.",
      "Brush with BBQ sauce and olive oil.",
      "Cook 18 to 20 minutes, turning halfway.",
      "Serve warm."
    ],
    kid_rating: 5,
    tips: [
      "Soak wooden skewers in water first to prevent burning.",
      "Serve with cucumber sticks."
    ]
  },
  {
    id: 9,
    name: "Strawberry Banana Smoothie",
    image: "https://images.unsplash.com/photo-1553530666-ba11a7da3888?w=800&q=80",
    gluten_free: true,
    egg_free: true,
    servings: 2,
    prep_time_minutes: 5,
    cook_time_minutes: 0,
    total_time_minutes: 5,
    ingredients: [
      "Frozen strawberries",
      "Banana",
      "Milk (or dairy-free milk)",
      "Honey or maple syrup (optional)"
    ],
    instructions: [
      "Add all ingredients into a blender.",
      "Blend until smooth.",
      "Pour into cups and serve."
    ],
    kid_rating: 5,
    tips: [
      "Add spinach for hidden greens.",
      "Add yogurt for extra creaminess."
    ]
  },
  {
    id: 10,
    name: "Gluten-Free Meatball Sliders",
    image: "https://images.unsplash.com/photo-1529692236671-f1f6cf9683ba?w=800&q=80",
    gluten_free: true,
    egg_free: true,
    servings: 4,
    prep_time_minutes: 15,
    cook_time_minutes: 20,
    total_time_minutes: 35,
    ingredients: [
      "Beef meatballs (egg-free, gluten-free)",
      "Gluten-free slider buns",
      "Tomato sauce",
      "Mozzarella cheese",
      "Italian herbs",
      "Olive oil"
    ],
    instructions: [
      "Preheat oven to 200°C.",
      "Cook meatballs in a pan with olive oil until browned.",
      "Add tomato sauce and simmer 5 minutes.",
      "Place meatballs into buns and top with cheese.",
      "Bake 5 minutes until cheese melts and serve."
    ],
    kid_rating: 5,
    tips: [
      "Use turkey meatballs for a lighter version.",
      "Serve with carrot sticks or oven fries."
    ]
  },
  {
    id: 11,
    name: "Sweet Potato & Black Bean Tacos",
    image: "https://images.unsplash.com/photo-1551504734-5e1f4dc88f52?w=800&q=80",
    gluten_free: true,
    egg_free: true,
    servings: 4,
    prep_time_minutes: 15,
    cook_time_minutes: 25,
    total_time_minutes: 40,
    ingredients: [
      "Sweet potatoes (diced)",
      "Black beans (tinned)",
      "Gluten-free soft tortillas",
      "Avocado",
      "Lime",
      "Cumin",
      "Salt",
      "Olive oil"
    ],
    instructions: [
      "Preheat oven to 200°C.",
      "Toss diced sweet potato with olive oil, cumin and salt. Roast 20 to 25 minutes.",
      "Warm black beans in a pan and mash slightly.",
      "Warm tortillas. Fill with sweet potato and beans.",
      "Top with avocado and a squeeze of lime. Serve."
    ],
    kid_rating: 4,
    tips: [
      "Add grated cheese if kids prefer.",
      "Serve with soured cream or yogurt."
    ]
  },
  {
    id: 12,
    name: "Honey Garlic Salmon Bites",
    image: "https://images.unsplash.com/photo-1467003909585-2f8a72700288?w=800&q=80",
    gluten_free: true,
    egg_free: true,
    servings: 4,
    prep_time_minutes: 10,
    cook_time_minutes: 12,
    total_time_minutes: 22,
    ingredients: [
      "Salmon fillets (cut into chunks)",
      "Honey",
      "Garlic (minced)",
      "Gluten-free soy sauce or tamari",
      "Sesame seeds",
      "Spring onions",
      "Olive oil"
    ],
    instructions: [
      "Mix honey, garlic and soy sauce in a small bowl.",
      "Heat olive oil in a pan over medium heat.",
      "Add salmon chunks and cook 2 to 3 minutes per side.",
      "Pour over honey garlic sauce and toss 1 minute.",
      "Sprinkle with sesame seeds and spring onion. Serve with rice."
    ],
    kid_rating: 4,
    tips: [
      "Use low-sodium soy sauce if preferred.",
      "Great with steamed broccoli."
    ]
  },
  {
    id: 13,
    name: "Banana Oat Pancakes",
    image: "https://images.unsplash.com/photo-1567620905732-2d1ec7ab7445?w=800&q=80",
    gluten_free: true,
    egg_free: true,
    servings: 4,
    prep_time_minutes: 10,
    cook_time_minutes: 15,
    total_time_minutes: 25,
    ingredients: [
      "Ripe bananas (mashed)",
      "Gluten-free oats (blended to flour)",
      "Milk (or dairy-free milk)",
      "Baking powder",
      "Cinnamon",
      "Maple syrup",
      "Oil for frying"
    ],
    instructions: [
      "Mash bananas in a bowl. Add oat flour, milk, baking powder and cinnamon. Mix well.",
      "Heat a little oil in a non-stick pan over medium heat.",
      "Spoon batter to make small pancakes. Cook 2 to 3 minutes per side.",
      "Stack and drizzle with maple syrup. Serve."
    ],
    kid_rating: 5,
    tips: [
      "Add blueberries to the batter for extra fruit.",
      "Keep warm in a low oven while you cook the rest."
    ]
  },
  {
    id: 14,
    name: "Lentil & Tomato Soup",
    image: "https://images.unsplash.com/photo-1547592166-23ac45744acd?w=800&q=80",
    gluten_free: true,
    egg_free: true,
    servings: 4,
    prep_time_minutes: 10,
    cook_time_minutes: 25,
    total_time_minutes: 35,
    ingredients: [
      "Red lentils",
      "Tinned chopped tomatoes",
      "Onion",
      "Carrot",
      "Vegetable stock",
      "Garlic",
      "Cumin",
      "Salt",
      "Pepper"
    ],
    instructions: [
      "Chop onion, carrot and garlic. Heat a little oil in a large pot.",
      "Fry onion and garlic 2 minutes. Add carrot and cumin, stir 1 minute.",
      "Add lentils, tomatoes and stock. Bring to the boil, then simmer 20 minutes.",
      "Season with salt and pepper. Blend if you like it smooth, or leave chunky. Serve."
    ],
    kid_rating: 4,
    tips: [
      "Serve with gluten-free bread or crackers.",
      "Stir in spinach at the end for extra greens."
    ]
  },
  {
    id: 15,
    name: "Cheese & Veggie Muffins",
    image: "https://images.unsplash.com/photo-1607958996333-5a2b763d3547?w=800&q=80",
    gluten_free: true,
    egg_free: true,
    servings: 12,
    prep_time_minutes: 15,
    cook_time_minutes: 20,
    total_time_minutes: 35,
    ingredients: [
      "Gluten-free self-raising flour",
      "Grated cheddar",
      "Grated carrot",
      "Grated courgette",
      "Milk (or dairy-free milk)",
      "Olive oil",
      "Baking powder",
      "Salt"
    ],
    instructions: [
      "Preheat oven to 180°C. Line a 12-hole muffin tin.",
      "Mix flour, baking powder and salt in a bowl.",
      "Stir in cheese, carrot and courgette. Add milk and oil, mix until just combined.",
      "Spoon into cases. Bake 18 to 20 minutes until golden and firm.",
      "Cool slightly and serve."
    ],
    kid_rating: 5,
    tips: [
      "Freeze extras for lunchboxes.",
      "Add sweetcorn or peas for more veg."
    ]
  },
  {
    id: 16,
    name: "Turkey & Sweetcorn Wraps",
    image: "https://images.unsplash.com/photo-1626700051175-6818013e1d4f?w=800&q=80",
    gluten_free: true,
    egg_free: true,
    servings: 4,
    prep_time_minutes: 10,
    cook_time_minutes: 5,
    total_time_minutes: 15,
    ingredients: [
      "Gluten-free wraps",
      "Cooked turkey (sliced or shredded)",
      "Sweetcorn (tinned or frozen)",
      "Lettuce",
      "Cherry tomatoes",
      "Mayonnaise or yogurt",
      "Salt",
      "Pepper"
    ],
    instructions: [
      "Warm the wraps briefly in a dry pan or microwave.",
      "Lay wraps flat. Add lettuce, turkey and sweetcorn.",
      "Slice cherry tomatoes and scatter on top.",
      "Add a drizzle of mayo or yogurt. Season, roll up and serve."
    ],
    kid_rating: 5,
    tips: [
      "Swap turkey for chicken or ham.",
      "Add grated cheese for a heartier wrap."
    ]
  },
  {
    id: 17,
    name: "Apple & Cinnamon Rice Pudding",
    image: "https://images.unsplash.com/photo-1517686469429-8bdb88b9f907?w=800&q=80",
    gluten_free: true,
    egg_free: true,
    servings: 4,
    prep_time_minutes: 5,
    cook_time_minutes: 30,
    total_time_minutes: 35,
    ingredients: [
      "Pudding rice or short-grain rice",
      "Milk (or dairy-free milk)",
      "Apple (peeled and diced)",
      "Cinnamon",
      "Honey or maple syrup",
      "Vanilla extract"
    ],
    instructions: [
      "Put rice, milk, apple and cinnamon in a pan. Bring to a gentle simmer.",
      "Stir often and cook 25 to 30 minutes until rice is tender and creamy.",
      "Stir in honey or maple syrup and vanilla. Add more milk if too thick.",
      "Serve warm, with extra cinnamon on top if you like."
    ],
    kid_rating: 5,
    tips: [
      "Great for breakfast or dessert.",
      "Add raisins or sultanas for extra sweetness."
    ]
  },
  {
    id: 18,
    name: "Veggie Fried Rice",
    image: "https://images.unsplash.com/photo-1603133872878-684f208fb84b?w=800&q=80",
    gluten_free: true,
    egg_free: true,
    servings: 4,
    prep_time_minutes: 15,
    cook_time_minutes: 10,
    total_time_minutes: 25,
    ingredients: [
      "Cooked rice (cold works best)",
      "Peas",
      "Sweetcorn",
      "Grated carrot",
      "Gluten-free soy sauce or tamari",
      "Spring onions",
      "Garlic",
      "Sesame oil",
      "Vegetable oil"
    ],
    instructions: [
      "Heat vegetable oil in a large pan or wok over high heat.",
      "Add garlic and spring onion, stir 30 seconds. Add carrot, peas and sweetcorn, stir 2 minutes.",
      "Add cold rice and break up any lumps. Stir-fry 3 to 4 minutes.",
      "Drizzle with soy sauce and a little sesame oil. Toss and serve."
    ],
    kid_rating: 4,
    tips: [
      "Use day-old rice for best results.",
      "Add cooked chicken or prawns for extra protein."
    ]
  },
  {
    id: 19,
    name: "Chocolate Banana Nice Cream",
    image: "https://images.unsplash.com/photo-1579952363873-27f3bade9f55?w=800&q=80",
    gluten_free: true,
    egg_free: true,
    servings: 4,
    prep_time_minutes: 5,
    cook_time_minutes: 0,
    total_time_minutes: 5,
    ingredients: [
      "Ripe bananas (frozen)",
      "Cocoa powder",
      "Milk (or dairy-free milk)",
      "Honey or maple syrup (optional)"
    ],
    instructions: [
      "Break frozen bananas into chunks and add to a blender.",
      "Add cocoa powder and a splash of milk. Blend until smooth and creamy.",
      "Taste and add honey or maple syrup if you want it sweeter.",
      "Scoop into bowls and serve straight away."
    ],
    kid_rating: 5,
    tips: [
      "Freeze bananas in advance for best texture.",
      "Top with berries or gluten-free granola."
    ]
  },
  {
    id: 20,
    name: "Sausage & Bean One-Pot",
    image: "https://images.unsplash.com/photo-1546069901-d5bfd2cbfb1f?w=800&q=80",
    gluten_free: true,
    egg_free: true,
    servings: 4,
    prep_time_minutes: 10,
    cook_time_minutes: 25,
    total_time_minutes: 35,
    ingredients: [
      "Gluten-free sausages",
      "Tinned cannellini or butter beans",
      "Tinned chopped tomatoes",
      "Onion",
      "Bell pepper",
      "Garlic",
      "Paprika",
      "Salt",
      "Olive oil"
    ],
    instructions: [
      "Brown sausages in a large pan with a little oil. Remove and slice into chunks.",
      "In the same pan, fry chopped onion and pepper 5 minutes. Add garlic and paprika, stir 1 minute.",
      "Add tomatoes and beans. Bring to a simmer, add sausage chunks back in.",
      "Simmer 15 to 20 minutes until thickened. Season and serve with mash or bread."
    ],
    kid_rating: 5,
    tips: [
      "Use gluten-free sausages and check labels.",
      "Add a pinch of sugar if the tomatoes taste sharp."
    ]
  }
];
