/**
 * Mock menu data for demo
 * Prices are stored in cents for precise calculations
 */
export const MOCK_MENU_ITEMS = [
  {
    id: 'item-001',
    category: 'Pizza',
    name: 'Margherita Pizza',
    description: 'Fresh mozzarella, tomato sauce, basil',
    price_cents: 1400,
    image_url: '/assets/images/margherita.jpg'
  },
  {
    id: 'item-002',
    category: 'Pizza',
    name: 'Pepperoni Pizza',
    description: 'Classic pepperoni with mozzarella',
    price_cents: 1600,
    image_url: '/assets/images/pepperoni.jpg'
  },
  {
    id: 'item-005',
    category: 'Pizza',
    name: 'Vegetarian Supreme',
    description: 'Mushrooms, peppers, onions, olives, tomatoes',
    price_cents: 1500,
    image_url: '/assets/images/veggie.jpg'
  },
  {
    id: 'item-003',
    category: 'Appetizers',
    name: 'Garlic Bread',
    description: 'Toasted bread with garlic butter',
    price_cents: 600,
    image_url: '/assets/images/garlic-bread.jpg'
  },
  {
    id: 'item-006',
    category: 'Appetizers',
    name: 'Mozzarella Sticks',
    description: 'Crispy breaded mozzarella with marinara',
    price_cents: 800,
    image_url: '/assets/images/mozz-sticks.jpg'
  },
  {
    id: 'item-007',
    category: 'Appetizers',
    name: 'Caesar Salad',
    description: 'Romaine lettuce, croutons, parmesan, caesar dressing',
    price_cents: 900,
    image_url: '/assets/images/caesar.jpg'
  },
  {
    id: 'item-004',
    category: 'Beverages',
    name: 'Coca-Cola',
    description: 'Classic Coca-Cola (12 oz)',
    price_cents: 300,
    image_url: '/assets/images/coke.jpg'
  },
  {
    id: 'item-008',
    category: 'Beverages',
    name: 'Sprite',
    description: 'Refreshing lemon-lime soda (12 oz)',
    price_cents: 300,
    image_url: '/assets/images/sprite.jpg'
  },
  {
    id: 'item-009',
    category: 'Beverages',
    name: 'Iced Tea',
    description: 'Freshly brewed iced tea (16 oz)',
    price_cents: 350,
    image_url: '/assets/images/iced-tea.jpg'
  }
];

/**
 * Group menu items by category
 * @param {Array} items - Menu items
 * @returns {Object} Items grouped by category
 */
export function groupByCategory(items) {
  return items.reduce((grouped, item) => {
    const category = item.category || 'Other';
    if (!grouped[category]) {
      grouped[category] = [];
    }
    grouped[category].push(item);
    return grouped;
  }, {});
}
