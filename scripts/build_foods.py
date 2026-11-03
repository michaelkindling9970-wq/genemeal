"""Builds reference/foods.json, the diet-builder food pool.

Each row is one MyPlate equivalent (oils: one teaspoon) of a common food:
  name | serving qty | serving unit | subgroup | protein g | fiber g | sat fat g | sodium mg | tags
Serving sizes follow the MyPlate food-group pages ("what counts as" tables);
nutrients are rounded from USDA FoodData Central (SR Legacy / FNDDS) for that
serving. Values are approximate and educational. Re-run after editing:
    python scripts/build_foods.py
Tags: gluten, lactose, caffeine (used to filter by genotype) and
omega3, vitamin_d, folate, carotenoid (used to star matches).
"""
import json
from pathlib import Path

SOURCES = [
    "https://www.myplate.gov/eat-healthy/fruits",
    "https://www.myplate.gov/eat-healthy/vegetables",
    "https://www.myplate.gov/eat-healthy/grains",
    "https://www.myplate.gov/eat-healthy/protein-foods",
    "https://www.myplate.gov/eat-healthy/dairy",
    "https://www.myplate.gov/eat-healthy/oils",
    "https://fdc.nal.usda.gov/",
    "https://www.dietaryguidelines.gov/sites/default/files/2020-12/Dietary_Guidelines_for_Americans_2020-2025.pdf",
]

PORTIONS = {"fruits": [0.5, 1, 1.5], "vegetables": [0.5, 1, 1.5], "grains": [1, 2, 3],
            "protein_foods": [1, 2, 3, 4], "dairy": [0.5, 0.75, 1, 1.5, 2], "oils": [1, 2, 3], "beverages": [8, 12, 16]}

RAW = {
"fruits": """
Apple|1|small|whole|0.4|3.6|0|1|
Banana|1|large|whole|1.5|3.5|0.1|1|
Orange|1|large|whole|1.7|4.4|0|0|folate
Grapefruit|1|medium|whole|1.5|3.7|0|0|carotenoid
Pear|1|medium|whole|0.6|5.5|0|2|
Peach|1|large|whole|1.4|2.3|0|0|carotenoid
Nectarine|1|large|whole|1.5|2.4|0|0|carotenoid
Plums|3|medium|whole|1.4|2.8|0|0|
Kiwifruit|2|medium|whole|1.6|4.2|0|4|folate
Mango, sliced|1|cup|whole|1.4|2.6|0.1|2|carotenoid folate
Papaya, cubed|1|cup|whole|0.7|2.5|0.1|11|carotenoid folate
Pineapple chunks|1|cup|whole|0.9|2.3|0|2|
Cantaloupe, cubed|1|cup|whole|1.3|1.4|0.1|26|carotenoid
Honeydew, cubed|1|cup|whole|0.9|1.4|0|31|
Watermelon, diced|1|cup|whole|0.9|0.6|0|2|carotenoid
Strawberries|1|cup|whole|1|3|0|1|folate
Blueberries|1|cup|whole|1.1|3.6|0|1|
Raspberries|1|cup|whole|1.5|8|0|1|
Blackberries|1|cup|whole|2|7.6|0|1|
Cherries, sweet|1|cup|whole|1.5|3|0.1|0|
Grapes|1|cup|whole|1.1|1.4|0.1|3|
Apricots|4|medium|whole|2|2.8|0|1|carotenoid
Tangerines|2|small|whole|1.5|3.2|0|4|carotenoid
Clementines|2|medium|whole|1.3|2.6|0|2|
Pomegranate arils|1|cup|whole|2.9|7|0.2|5|folate
Figs, fresh|2|large|whole|1|3.7|0|1|
Guava|1|cup|whole|4.2|8.9|0.5|3|carotenoid folate
Persimmon|1|medium|whole|1|6|0|2|carotenoid
Plantain, cooked|1|cup|whole|1.2|3.5|0.1|8|carotenoid
Starfruit, sliced|1|cup|whole|1.1|3.1|0|2|
Lychee|1|cup|whole|1.6|2.5|0.2|2|
Mixed fruit, canned in juice|1|cup|canned|1|2.5|0|10|
Peaches, canned in juice|1|cup|canned|1.1|3.2|0|10|carotenoid
Pears, canned in juice|1|cup|canned|0.8|4|0|10|
Mandarin oranges, canned in juice|1|cup|canned|1.5|1.8|0|12|carotenoid
Applesauce, unsweetened|1|cup|canned|0.4|2.7|0|5|
Pineapple, canned in juice|1|cup|canned|1|2|0|2|
Frozen mixed berries|1|cup|frozen|1|5|0|2|
Frozen mango chunks|1|cup|frozen|1.3|2.6|0|2|carotenoid
Frozen cherries, unsweetened|1|cup|frozen|1.5|3|0.1|0|
Raisins|0.5|cup|dried|2.5|3.3|0|9|
Dried apricots|0.5|cup|dried|2.2|4.7|0|6|carotenoid
Prunes|0.5|cup|dried|1.9|6.2|0|2|
Dates, chopped|0.5|cup|dried|1.8|6|0|2|
Dried cranberries|0.5|cup|dried|0.1|3|0|3|
Dried figs|0.5|cup|dried|2.5|7.3|0.1|8|
Dried mango|0.5|cup|dried|1.2|2|0.1|80|carotenoid
Orange juice, 100%|1|cup|juice|1.7|0.5|0|2|folate
Apple juice, 100%|1|cup|juice|0.2|0.5|0|10|
Grape juice, 100%|1|cup|juice|0.9|0.5|0|10|
Grapefruit juice, 100%|1|cup|juice|1.2|0.2|0|2|
Pineapple juice, 100%|1|cup|juice|0.9|0.5|0|5|
Tart cherry juice, 100%|1|cup|juice|1|0|0|10|
Pomegranate juice, 100%|1|cup|juice|0.4|0.3|0|22|
""",
"vegetables": """
Spinach, raw|2|cups|dark green|1.7|1.3|0|47|folate carotenoid
Spinach, cooked|1|cup|dark green|5.3|4.3|0.1|126|folate carotenoid
Kale, raw|2|cups|dark green|2.6|1.8|0.1|30|carotenoid
Kale, cooked|1|cup|dark green|3.5|4.7|0.1|30|carotenoid
Broccoli|1|cup|dark green|3.7|5.1|0.1|64|folate carotenoid
Romaine lettuce|2|cups|dark green|1.2|2|0|8|folate carotenoid
Collard greens, cooked|1|cup|dark green|5|7.6|0.2|30|folate carotenoid
Swiss chard, cooked|1|cup|dark green|3.3|3.7|0|313|carotenoid
Bok choy, cooked|1|cup|dark green|2.7|1.7|0|58|folate carotenoid
Arugula|2|cups|dark green|1|0.6|0|11|folate
Mustard greens, cooked|1|cup|dark green|3.5|2.8|0|22|folate carotenoid
Turnip greens, cooked|1|cup|dark green|1.6|5|0.1|42|folate carotenoid
Watercress|2|cups|dark green|1.6|0.4|0|28|carotenoid
Mesclun / spring mix|2|cups|dark green|1.8|1.8|0|30|folate carotenoid
Broccoli rabe, cooked|1|cup|dark green|4.5|3.5|0.1|56|folate
Carrots|1|cup|red & orange|1.2|3.6|0|88|carotenoid
Baby carrots|1|cup|red & orange|0.9|4|0|102|carotenoid
Sweet potato, baked|1|cup|red & orange|4|6.6|0.1|72|carotenoid
Tomatoes|1|cup|red & orange|1.6|2.2|0|9|carotenoid
Cherry tomatoes|1|cup|red & orange|1.3|1.8|0|7|carotenoid
Red bell pepper|1|cup|red & orange|1.5|3.1|0.1|6|carotenoid
Butternut squash, cooked|1|cup|red & orange|1.8|6.6|0|8|carotenoid
Pumpkin, cooked|1|cup|red & orange|1.8|2.7|0.1|2|carotenoid
Acorn squash, cooked|1|cup|red & orange|2.3|9|0.1|8|carotenoid
Tomato juice, low sodium|1|cup|red & orange|1.9|1|0|24|carotenoid
Tomato sauce, no salt added|1|cup|red & orange|3.2|3.7|0|26|carotenoid
Salsa, fresh|1|cup|red & orange|2.5|3|0|430|carotenoid
Roasted red peppers|1|cup|red & orange|1.5|2.5|0|380|carotenoid
Black beans, cooked|1|cup|beans, peas, lentils|15|15|0.2|2|folate
Kidney beans, cooked|1|cup|beans, peas, lentils|15|13|0.1|4|folate
Pinto beans, cooked|1|cup|beans, peas, lentils|15|15|0.2|2|folate
Chickpeas, cooked|1|cup|beans, peas, lentils|14.5|12.5|0.4|11|folate
Lentils, cooked|1|cup|beans, peas, lentils|18|15.6|0.1|4|folate
Split peas, cooked|1|cup|beans, peas, lentils|16|16|0.1|4|folate
Navy beans, cooked|1|cup|beans, peas, lentils|15|19|0.3|2|folate
Great northern beans, cooked|1|cup|beans, peas, lentils|15|12|0.2|4|folate
Lima beans, cooked|1|cup|beans, peas, lentils|12|9|0.1|4|folate
Black-eyed peas, cooked|1|cup|beans, peas, lentils|13|11|0.2|7|folate
Edamame|1|cup|beans, peas, lentils|18|8|0.6|9|folate
Pigeon peas, cooked|1|cup|beans, peas, lentils|11|11|0.2|8|folate
Refried beans, canned|1|cup|beans, peas, lentils|13|11|0.5|1000|folate
Canned black beans, rinsed|1|cup|beans, peas, lentils|14|15|0.2|300|folate
Potato, baked with skin|1|cup|starchy|3|3|0|10|
Corn kernels|1|cup|starchy|4.7|3.3|0.3|2|carotenoid
Green peas|1|cup|starchy|8.6|8.8|0.1|5|folate carotenoid
Parsnips, cooked|1|cup|starchy|2|6|0.1|16|folate
Yuca / cassava, cooked|1|cup|starchy|1.9|2.5|0.1|19|
Taro, cooked|1|cup|starchy|0.7|6.7|0|20|
Green banana, cooked|1|cup|starchy|1.6|3|0.1|4|
Water chestnuts|1|cup|starchy|1.4|3.6|0|11|
Red potatoes, roasted|1|cup|starchy|3|2.6|0|15|
Hash browns, homemade|1|cup|starchy|3|3|2|30|
Mashed potatoes, with milk|1|cup|starchy|4|3|0.7|630|lactose
Cauliflower|1|cup|other|2|2|0|30|folate
Green beans|1|cup|other|2|4|0.1|1|carotenoid
Zucchini|1|cup|other|1.4|1.2|0.1|10|carotenoid
Yellow squash|1|cup|other|1.4|1.2|0.1|10|
Cucumber|1|cup|other|0.7|0.5|0|2|
Celery|1|cup|other|0.7|1.6|0|81|folate
Onions|1|cup|other|1.8|2.7|0|6|
Mushrooms|1|cup|other|2.2|0.7|0|4|vitamin_d
Mushrooms, UV-exposed|1|cup|other|2.2|0.7|0|4|vitamin_d
Asparagus|1|cup|other|3|3|0|3|folate carotenoid
Brussels sprouts|1|cup|other|4|4|0.1|26|folate
Cabbage, shredded|1|cup|other|0.9|1.8|0|13|folate
Red cabbage, shredded|1|cup|other|1|1.9|0|24|
Eggplant, cooked|1|cup|other|0.8|2.5|0|2|
Green bell pepper|1|cup|other|1.3|2.5|0.1|4|
Beets, cooked|1|cup|other|2.9|3.4|0|131|folate
Okra, cooked|1|cup|other|3|4|0.1|10|folate
Artichoke hearts|1|cup|other|4|9|0|120|folate
Snow peas / snap peas|1|cup|other|2.8|2.6|0|4|carotenoid
Bean sprouts|1|cup|other|3|1.9|0|6|folate
Iceberg lettuce|2|cups|other|1|1.4|0|14|
Radishes|1|cup|other|0.8|1.9|0|45|
Jicama|1|cup|other|1|6.4|0|5|
Turnips, cooked|1|cup|other|1.1|3.1|0|25|
Fennel bulb|1|cup|other|1.1|2.7|0|45|
Leeks, cooked|1|cup|other|0.8|1|0|10|folate
Kohlrabi|1|cup|other|2.3|4.9|0|27|
Avocado, cubed|1|cup|other|3|10|3.2|10|folate
Sauerkraut|1|cup|other|1.3|4|0|940|
Vegetable soup, low sodium|1|cup|other|3|2|0.3|200|carotenoid
Mixed frozen vegetables|1|cup|other|5|7|0.1|64|carotenoid
Stir-fry vegetable blend|1|cup|other|2.5|3|0.1|40|carotenoid
Vegetable juice, low sodium|1|cup|other|1.5|1.9|0|140|carotenoid
Kimchi|1|cup|other|2|2.4|0|750|
""",
"grains": """
Brown rice, cooked|0.5|cup|whole|2.5|1.8|0.2|5|
Wild rice, cooked|0.5|cup|whole|3.3|1.5|0|3|folate
Black rice, cooked|0.5|cup|whole|3|1.5|0.2|5|
Red rice, cooked|0.5|cup|whole|2.5|1.6|0.2|5|
Quinoa, cooked|0.5|cup|whole|4|2.6|0.2|7|folate
Millet, cooked|0.5|cup|whole|3|1.1|0.1|2|
Sorghum, cooked|0.5|cup|whole|3.5|2.5|0.1|2|
Buckwheat groats (kasha), cooked|0.5|cup|whole|2.8|2.3|0.1|3|
Amaranth, cooked|0.5|cup|whole|4.7|2.6|0.2|7|folate
Teff, cooked|0.5|cup|whole|4.9|3.5|0.1|10|
Oatmeal, cooked|0.5|cup|whole|3|2|0.2|5|
Steel-cut oats, cooked|0.5|cup|whole|3|2.5|0.3|0|
Oat bran, cooked|0.5|cup|whole|3.5|2.9|0.2|1|
Rolled oats, dry|0.333|cup|whole|3.5|2.7|0.3|2|
Popcorn, air-popped|3|cups|whole|3|3.5|0.1|2|
Corn tortilla|1|6-inch|whole|1.5|1.5|0.1|10|
Whole-grain cornmeal / polenta, cooked|0.5|cup|whole|2|1.5|0.1|5|
Brown rice cakes|2|cakes|whole|1.4|0.8|0.1|10|
Brown rice pasta, cooked|0.5|cup|whole|2.5|1.5|0.1|2|
Brown rice noodles, cooked|0.5|cup|whole|2|1|0.1|10|
Fonio, cooked|0.5|cup|whole|2|1|0|2|
Gluten-free whole-grain bread|1|slice|whole|2|2|0.2|140|
Puffed brown rice cereal|1|cup|whole|1.5|0.8|0.1|1|
Oat-based O's cereal|1|cup|whole|3|2.8|0.3|140|
Corn grits, whole-grain, cooked|0.5|cup|whole|1.8|1|0.1|3|
Whole-wheat bread|1|slice|whole|3.6|1.9|0.3|130|gluten
Whole-wheat pita|1|small|whole|3.5|2.5|0.2|170|gluten
Whole-wheat tortilla|1|small|whole|3|2.5|0.5|200|gluten
Whole-wheat pasta, cooked|0.5|cup|whole|3.7|3.2|0.1|2|gluten
Bulgur, cooked|0.5|cup|whole|2.8|4.1|0|5|gluten
Farro, cooked|0.5|cup|whole|3.5|2.5|0.1|5|gluten
Barley, cooked|0.5|cup|whole|1.8|3|0.1|2|gluten
Whole-wheat couscous, cooked|0.5|cup|whole|3|3|0.1|5|gluten
Freekeh, cooked|0.5|cup|whole|4|4|0.1|5|gluten
Whole-wheat English muffin|0.5|muffin|whole|3|2.2|0.2|210|gluten
Whole-grain crackers|5|crackers|whole|2|2|0.4|150|gluten
Shredded wheat cereal|1|cup|whole|5|6|0.2|0|gluten
Bran flakes|1|cup|whole|3.5|7|0.2|230|gluten
Rye bread, whole-grain|1|slice|whole|2.7|1.9|0.2|190|gluten
Whole-wheat bagel|0.25|bagel|whole|2.5|1.7|0.1|110|gluten
White rice, cooked|0.5|cup|refined|2.1|0.3|0.1|1|folate
Jasmine rice, cooked|0.5|cup|refined|2|0.3|0.1|1|
Basmati rice, cooked|0.5|cup|refined|2.2|0.4|0.1|1|
Rice noodles, cooked|0.5|cup|refined|0.8|0.8|0|17|
Plain rice cakes|2|cakes|refined|1.4|0.4|0.1|10|
Cream of rice, cooked|0.5|cup|refined|1|0.1|0|1|
Corn flakes, gluten-free|1|cup|refined|1.6|0.7|0.1|200|folate
Crispy rice cereal, gluten-free|1|cup|refined|1.5|0.2|0.1|170|folate
Polenta / degermed cornmeal, cooked|0.5|cup|refined|1.5|0.6|0|2|
Corn arepa|0.5|arepa|refined|1.8|1|0.2|120|
Gluten-free white bread|1|slice|refined|1.5|1|0.3|160|
Rice vermicelli, cooked|0.5|cup|refined|0.9|0.5|0|10|
Hominy, cooked|0.5|cup|refined|1.2|2|0.1|170|
White bread|1|slice|refined|2.3|0.7|0.2|140|gluten folate
White pasta, cooked|0.5|cup|refined|3.6|1.2|0.1|1|gluten folate
Flour tortilla|1|small|refined|2.5|0.7|0.9|260|gluten
Bagel, plain|0.25|bagel|refined|2.5|0.6|0.1|110|gluten
English muffin|0.5|muffin|refined|2.2|0.8|0.1|120|gluten
Pita, white|1|small|refined|2.5|0.7|0.1|160|gluten
Couscous, cooked|0.5|cup|refined|3|1.1|0|4|gluten
Egg noodles, cooked|0.5|cup|refined|3.6|1.2|0.2|4|gluten
Saltine crackers|7|crackers|refined|2|0.6|0.4|280|gluten
Pretzels|0.75|oz|refined|2|0.6|0|380|gluten
Pancake, plain|1|4-inch|refined|2.4|0.5|0.6|240|gluten lactose
Waffle, frozen|1|4-inch|refined|2|0.7|0.7|250|gluten lactose
Biscuit|1|small|refined|2|0.5|2.6|350|gluten lactose
Dinner roll|1|small|refined|2.4|0.8|0.4|140|gluten
Croissant|1|small|refined|4|1.4|6|210|gluten lactose
""",
"protein_foods": """
Chicken breast, skinless|1|oz|meats, poultry, eggs|8.8|0|0.3|21|
Chicken thigh, skinless|1|oz|meats, poultry, eggs|7.5|0|0.7|30|
Turkey breast, roasted|1|oz|meats, poultry, eggs|8.5|0|0.2|20|
Ground turkey, 93% lean|1|oz|meats, poultry, eggs|7.5|0|0.8|25|
Lean beef sirloin|1|oz|meats, poultry, eggs|8.5|0|0.8|18|
Lean ground beef, 93%|1|oz|meats, poultry, eggs|7.3|0|1.1|22|
Beef tenderloin|1|oz|meats, poultry, eggs|8|0|1.1|17|
Ribeye steak|1|oz|meats, poultry, eggs|6.8|0|2.6|17|
Ground beef, 80%|1|oz|meats, poultry, eggs|7|0|2.4|25|
Pork tenderloin|1|oz|meats, poultry, eggs|7.5|0|0.4|18|
Pork loin chop|1|oz|meats, poultry, eggs|8|0|0.8|18|
Lamb, lean leg|1|oz|meats, poultry, eggs|8|0|1|22|
Bison, ground|1|oz|meats, poultry, eggs|7.2|0|1|23|
Venison|1|oz|meats, poultry, eggs|8.6|0|0.5|19|
Egg, whole|1|large|meats, poultry, eggs|6.3|0|1.6|71|vitamin_d folate
Egg whites|2|large|meats, poultry, eggs|7.2|0|0|110|
Ham, deli|1|oz|meats, poultry, eggs|5|0|0.5|370|
Turkey, deli|1|oz|meats, poultry, eggs|5|0|0.2|300|
Bacon|1|oz|meats, poultry, eggs|10|0|3.9|520|
Pork sausage|1|oz|meats, poultry, eggs|5|0|2.6|230|
Chicken liver|1|oz|meats, poultry, eggs|7|0|0.5|22|folate carotenoid
Salmon, Atlantic|1|oz|seafood|7|0|0.6|17|omega3 vitamin_d
Sockeye salmon|1|oz|seafood|7.5|0|0.3|25|omega3 vitamin_d
Canned salmon|1|oz|seafood|6.5|0|0.4|100|omega3 vitamin_d
Sardines, canned|1|oz|seafood|7|0|0.4|86|omega3 vitamin_d
Mackerel, Atlantic|1|oz|seafood|6.7|0|1|26|omega3 vitamin_d
Rainbow trout|1|oz|seafood|7|0|0.5|20|omega3 vitamin_d
Herring|1|oz|seafood|6.5|0|0.8|33|omega3 vitamin_d
Anchovies, fresh|1|oz|seafood|5.8|0|0.4|29|omega3
Tuna, canned light in water|1|oz|seafood|7.2|0|0.1|70|omega3 vitamin_d
Tuna steak|1|oz|seafood|8.4|0|0.1|14|omega3
Cod|1|oz|seafood|6.5|0|0|22|
Tilapia|1|oz|seafood|7.4|0|0.3|16|
Halibut|1|oz|seafood|6.4|0|0.1|23|vitamin_d
Pollock|1|oz|seafood|6.9|0|0.1|30|omega3
Catfish|1|oz|seafood|5.3|0|0.4|20|vitamin_d
Haddock|1|oz|seafood|7|0|0|74|
Flounder / sole|1|oz|seafood|4.4|0|0.1|102|
Mahi-mahi|1|oz|seafood|6.7|0|0|32|
Shrimp|1|oz|seafood|6.8|0|0.1|60|
Scallops|1|oz|seafood|5.8|0|0|190|
Mussels|1|oz|seafood|6.7|0|0.2|105|omega3
Oysters|1|oz|seafood|5.5|0|0.3|120|omega3 vitamin_d
Clams|1|oz|seafood|7.2|0|0.1|170|
Crab|1|oz|seafood|5.5|0|0|110|omega3
Lobster|1|oz|seafood|5.4|0|0|135|
Black beans|0.25|cup|nuts, seeds, soy|3.8|3.8|0.1|1|folate
Chickpeas|0.25|cup|nuts, seeds, soy|3.6|3.1|0.1|3|folate
Lentils|0.25|cup|nuts, seeds, soy|4.5|3.9|0|1|folate
Kidney beans|0.25|cup|nuts, seeds, soy|3.8|3.3|0|1|folate
Pinto beans|0.25|cup|nuts, seeds, soy|3.8|3.8|0|1|folate
White beans|0.25|cup|nuts, seeds, soy|4.3|3.2|0|3|folate
Split peas|0.25|cup|nuts, seeds, soy|4|4|0|1|folate
Hummus|2|Tbsp|nuts, seeds, soy|2.4|1.8|0.4|130|folate
Tofu, firm|0.25|cup|nuts, seeds, soy|5.5|0.7|0.6|10|
Tempeh|1|oz|nuts, seeds, soy|5.5|1.6|0.6|3|
Edamame, shelled|0.25|cup|nuts, seeds, soy|4.6|2|0.2|2|folate
Soy nuts|0.5|oz|nuts, seeds, soy|5.7|1.2|0.5|1|
Seitan|1|oz|nuts, seeds, soy|7|0.2|0|120|gluten
Veggie burger, soy-based|1|oz|nuts, seeds, soy|4|1.2|0.3|130|
Almonds|0.5|oz|nuts, seeds, soy|3|1.8|0.3|0|
Walnuts|0.5|oz|nuts, seeds, soy|2.2|1|0.9|0|omega3
Pecans|0.5|oz|nuts, seeds, soy|1.3|1.4|0.9|0|
Pistachios|0.5|oz|nuts, seeds, soy|2.9|1.5|0.8|0|carotenoid
Cashews|0.5|oz|nuts, seeds, soy|2.6|0.5|1.1|2|
Peanuts|0.5|oz|nuts, seeds, soy|3.7|1.2|0.9|3|folate
Hazelnuts|0.5|oz|nuts, seeds, soy|2.1|1.4|0.6|0|folate
Macadamia nuts|0.5|oz|nuts, seeds, soy|1.1|1.2|1.7|0|
Brazil nuts|0.5|oz|nuts, seeds, soy|2|1|2.1|0|
Pine nuts|0.5|oz|nuts, seeds, soy|1.9|0.5|0.7|0|
Sunflower seeds|0.5|oz|nuts, seeds, soy|2.9|1.2|0.6|1|folate
Pumpkin seeds|0.5|oz|nuts, seeds, soy|4.2|0.8|1.2|1|
Chia seeds|0.5|oz|nuts, seeds, soy|2.3|4.9|0.5|2|omega3
Ground flaxseed|0.5|oz|nuts, seeds, soy|2.6|3.9|0.5|4|omega3
Hemp seeds|0.5|oz|nuts, seeds, soy|4.7|0.6|0.5|1|omega3
Sesame seeds|0.5|oz|nuts, seeds, soy|2.5|1.7|0.9|2|
Peanut butter|1|Tbsp|nuts, seeds, soy|3.6|1|1.6|70|
Almond butter|1|Tbsp|nuts, seeds, soy|3.4|1.6|0.7|1|
Sunflower seed butter|1|Tbsp|nuts, seeds, soy|2.8|0.9|0.7|50|
Tahini|1|Tbsp|nuts, seeds, soy|2.6|1.4|1|5|
""",
"dairy": """
Fat-free milk|1|cup|milk|8.3|0|0.1|103|lactose vitamin_d
Low-fat milk|1|cup|milk|8.2|0|1.5|107|lactose vitamin_d
Reduced-fat (2%) milk|1|cup|milk|8|0|3.1|115|lactose vitamin_d
Whole milk|1|cup|milk|7.7|0|4.6|105|lactose vitamin_d
Low-fat chocolate milk|1|cup|milk|8|1|1.5|150|lactose vitamin_d caffeine
Buttermilk, low-fat|1|cup|milk|8|0|1.3|260|lactose
Fat-free plain yogurt|1|cup|yogurt|14|0|0.3|190|lactose
Low-fat plain yogurt|1|cup|yogurt|13|0|2.3|170|lactose
Nonfat Greek yogurt|1|cup|yogurt|23|0|0.3|85|lactose
Low-fat fruit yogurt|1|cup|yogurt|10|0|1.8|140|lactose
Kefir, low-fat|1|cup|yogurt|9|0|1.5|125|lactose vitamin_d
Cheddar cheese|1.5|oz|cheese|10.5|0|8|270|lactose
Part-skim mozzarella|1.5|oz|cheese|10.3|0|4.3|260|lactose
Swiss cheese|1.5|oz|cheese|11.5|0|7.5|80|lactose
Provolone|1.5|oz|cheese|10.8|0|7|370|lactose
Low-fat cottage cheese|2|cups|cheese|28|0|2.9|1840|lactose
Part-skim ricotta|1|cup|cheese|28|0|12|300|lactose
Feta|1.5|oz|cheese|6|0|6.3|470|lactose
Lactose-free fat-free milk|1|cup|lactose-free|8.3|0|0.1|125|lactose_free vitamin_d
Lactose-free low-fat milk|1|cup|lactose-free|8.2|0|1.5|125|lactose_free vitamin_d
Lactose-free reduced-fat milk|1|cup|lactose-free|8|0|3|125|lactose_free vitamin_d
Lactose-free low-fat chocolate milk|1|cup|lactose-free|8|1|1.5|160|lactose_free vitamin_d caffeine
Lactose-free fat-free plain yogurt|1|cup|lactose-free|12|0|0.2|160|lactose_free
Lactose-free low-fat vanilla yogurt|1|cup|lactose-free|10|0|1.8|140|lactose_free
Lactose-free nonfat Greek yogurt|1|cup|lactose-free|22|0|0.3|90|lactose_free
Lactose-free low-fat kefir|1|cup|lactose-free|10|0|1.5|130|lactose_free vitamin_d
Lactose-free low-fat cottage cheese|2|cups|lactose-free|26|0|3|1500|lactose_free
Parmesan, grated (naturally ~lactose-free)|0.333|cup|lactose-free|10|0|5|510|lactose_free
Fortified soy milk|1|cup|fortified soy|8|1|0.5|90|lactose_free vitamin_d
Fortified soy milk, unsweetened|1|cup|fortified soy|7|1|0.5|85|lactose_free vitamin_d
Fortified soy milk, vanilla|1|cup|fortified soy|6|1|0.5|95|lactose_free vitamin_d
Fortified soy milk, light|1|cup|fortified soy|6|1|0.3|110|lactose_free vitamin_d
Fortified soy milk, chocolate|1|cup|fortified soy|6|2|0.5|150|lactose_free vitamin_d
Fortified soy yogurt, plain|1|cup|fortified soy|9|1.5|0.5|30|lactose_free vitamin_d
Fortified soy yogurt, vanilla|1|cup|fortified soy|8|1.5|0.5|40|lactose_free vitamin_d
Fortified soy Greek-style yogurt|1|cup|fortified soy|20|1|0.5|60|lactose_free vitamin_d
""",
"oils": """
Olive oil|1|tsp|oil|0|0|0.6|0|
Extra-virgin olive oil|1|tsp|oil|0|0|0.6|0|
Canola oil|1|tsp|oil|0|0|0.3|0|omega3
Soybean oil|1|tsp|oil|0|0|0.7|0|omega3
Corn oil|1|tsp|oil|0|0|0.6|0|
Sunflower oil|1|tsp|oil|0|0|0.5|0|
High-oleic sunflower oil|1|tsp|oil|0|0|0.4|0|
Safflower oil|1|tsp|oil|0|0|0.3|0|
High-oleic safflower oil|1|tsp|oil|0|0|0.3|0|
Peanut oil|1|tsp|oil|0|0|0.8|0|
Sesame oil|1|tsp|oil|0|0|0.6|0|
Toasted sesame oil|1|tsp|oil|0|0|0.6|0|
Avocado oil|1|tsp|oil|0|0|0.5|0|
Grapeseed oil|1|tsp|oil|0|0|0.4|0|
Walnut oil|1|tsp|oil|0|0|0.4|0|omega3
Flaxseed oil|1|tsp|oil|0|0|0.4|0|omega3
Almond oil|1|tsp|oil|0|0|0.4|0|
Rice bran oil|1|tsp|oil|0|0|0.9|0|
Hazelnut oil|1|tsp|oil|0|0|0.3|0|
Cottonseed oil|1|tsp|oil|0|0|1.2|0|
Coconut oil|1|tsp|solid fat (not an oil)|0|0|3.9|0|
Butter|1|tsp|solid fat (not an oil)|0|0|2.4|30|lactose
Soft tub margarine, trans-fat-free|1|tsp|oil-rich food|0|0|0.6|35|
Mayonnaise|1|tsp|oil-rich food|0|0|0.5|30|
Light mayonnaise|2|tsp|oil-rich food|0|0|0.6|80|
Olive oil mayonnaise|1|tsp|oil-rich food|0|0|0.4|35|
Italian dressing|2|tsp|oil-rich food|0|0|0.6|160|
Balsamic vinaigrette|2|tsp|oil-rich food|0|0|0.5|90|
Avocado, sliced|0.125|fruit|oil-rich food|0.5|1.7|0.5|2|folate
Olives, black|8|large|oil-rich food|0.3|1|0.6|280|
Pesto|1.5|tsp|oil-rich food|0.5|0.1|0.6|60|lactose
""",
"beverages": """
Water|1|fl oz|water|0|0|0|0|
Sparkling water, unflavored|1|fl oz|water|0|0|0|1|
Sparkling water, lemon|1|fl oz|water|0|0|0|1|
Mineral water|1|fl oz|water|0|0|0|2|
Cucumber-mint infused water|1|fl oz|water|0|0|0|0|
Coconut water|1|fl oz|water|0.1|0|0|30|
Peppermint tea|1|fl oz|caffeine-free tea|0|0|0|0|
Chamomile tea|1|fl oz|caffeine-free tea|0|0|0|0|
Rooibos tea|1|fl oz|caffeine-free tea|0|0|0|0|
Hibiscus tea|1|fl oz|caffeine-free tea|0|0|0|0|
Ginger tea|1|fl oz|caffeine-free tea|0|0|0|0|
Lemon balm tea|1|fl oz|caffeine-free tea|0|0|0|0|
Fruit herbal tea|1|fl oz|caffeine-free tea|0|0|0|0|
Decaf coffee, black|1|fl oz|decaf|0|0|0|0|
Decaf espresso|1|fl oz|decaf|0.1|0|0|1|
Decaf black tea|1|fl oz|decaf|0|0|0|0|
Decaf green tea|1|fl oz|decaf|0|0|0|0|
Decaf iced tea, unsweetened|1|fl oz|decaf|0|0|0|1|
Barley-free chicory "coffee"|1|fl oz|decaf|0|0|0|1|
Decaf soy latte (fortified soy milk)|1|fl oz|decaf|0.8|0.1|0.1|12|lactose_free
Golden milk, fortified soy|1|fl oz|decaf|0.8|0.1|0.1|12|lactose_free
Tomato juice, low sodium (drink)|1|fl oz|other|0.2|0.1|0|3|
Kombucha, decaf|1|fl oz|other|0|0|0|1|
Coffee, brewed|1|fl oz|caffeinated|0|0|0|1|caffeine
Espresso|1|fl oz|caffeinated|0.1|0|0|4|caffeine
Cold brew coffee|1|fl oz|caffeinated|0|0|0|1|caffeine
Black tea|1|fl oz|caffeinated|0|0|0|0|caffeine
Green tea|1|fl oz|caffeinated|0|0|0|0|caffeine
Matcha|1|fl oz|caffeinated|0.1|0|0|0|caffeine
Yerba mate|1|fl oz|caffeinated|0|0|0|0|caffeine
Iced tea, unsweetened|1|fl oz|caffeinated|0|0|0|1|caffeine
Cola|1|fl oz|caffeinated|0|0|0|1|caffeine
Energy drink|1|fl oz|caffeinated|0|0|0|25|caffeine
Latte (dairy milk)|1|fl oz|caffeinated|0.8|0|0.3|12|caffeine lactose
""",
}

# grams of oil per row (oils group unit is grams; 1 tsp oil ~ 4.5 g)
OIL_GRAMS = {"Light mayonnaise": 4, "Italian dressing": 4, "Balsamic vinaigrette": 4,
             "Avocado, sliced": 5, "Olives, black": 4, "Pesto": 4, "Butter": 4,
             "Soft tub margarine, trans-fat-free": 3.5, "Mayonnaise": 4,
             "Olive oil mayonnaise": 4}


def rows():
    out = {}
    for group, text in RAW.items():
        items = []
        for line in text.strip().splitlines():
            name, qty, unit, sub, p, f, sf, na, tags = line.split("|")
            items.append({
                "name": name, "qty": float(qty), "unit": unit, "subgroup": sub,
                "eq": OIL_GRAMS.get(name, 4.5) if group == "oils" else 1,
                "protein_g": float(p), "fiber_g": float(f), "sat_fat_g": float(sf),
                "sodium_mg": float(na), "tags": tags.split(),
            })
        out[group] = items
    return out


if __name__ == "__main__":
    doc = {
        "note": ("One row = one MyPlate equivalent (oils: grams in the listed serving). "
                 "Serving sizes from the MyPlate 'what counts as' pages; nutrients rounded "
                 "from USDA FoodData Central. Approximate and educational; the build box "
                 "could not fetch myplate.gov on 2026-11-02, so values were transcribed "
                 "from the published USDA tables."),
        "sources": SOURCES, "portions": PORTIONS, "foods": rows(),
    }
    path = Path(__file__).resolve().parents[1] / "reference" / "foods.json"
    path.write_text(json.dumps(doc, indent=1) + "\n")
    print({g: len(v) for g, v in doc["foods"].items()})
