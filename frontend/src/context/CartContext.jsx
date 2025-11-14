import React, { createContext, useContext, useState, useEffect } from 'react';
import { CONFIG } from '../config/config';

/**
 * CartContext - Provides cart state management with localStorage persistence
 */
const CartContext = createContext();

const CART_STORAGE_KEY = 'demo_cart';

export function CartProvider({ children }) {
  const [cartItems, setCartItems] = useState(() => {
    // Load cart from localStorage on initial mount
    try {
      const stored = localStorage.getItem(CART_STORAGE_KEY);
      if (stored) {
        return JSON.parse(stored);
      }
    } catch (error) {
      console.error('Error loading cart from storage:', error);
    }
    return [];
  });

  // Save cart to localStorage whenever it changes
  useEffect(() => {
    try {
      localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(cartItems));
    } catch (error) {
      console.error('Error saving cart to storage:', error);
    }
  }, [cartItems]);

  const addToCart = (menuItem, quantity = 1) => {
    const existingItem = cartItems.find(i => i.menu_item_id === menuItem.id);

    if (existingItem) {
      setCartItems(cartItems.map(i =>
        i.menu_item_id === menuItem.id
          ? { ...i, quantity: i.quantity + quantity, subtotal_cents: (i.quantity + quantity) * i.unit_price_cents }
          : i
      ));
    } else {
      setCartItems([
        ...cartItems,
        {
          menu_item_id: menuItem.id,
          name: menuItem.name,
          quantity: quantity,
          unit_price_cents: menuItem.price_cents,
          subtotal_cents: menuItem.price_cents * quantity
        }
      ]);
    }
  };

  const removeFromCart = (menuItemId) => {
    setCartItems(cartItems.filter(i => i.menu_item_id !== menuItemId));
  };

  const updateQuantity = (menuItemId, quantity) => {
    if (quantity <= 0) {
      removeFromCart(menuItemId);
    } else {
      setCartItems(cartItems.map(i =>
        i.menu_item_id === menuItemId
          ? { ...i, quantity, subtotal_cents: i.unit_price_cents * quantity }
          : i
      ));
    }
  };

  const clearCart = () => {
    setCartItems([]);
  };

  const calculateTotals = () => {
    const subtotal_cents = cartItems.reduce(
      (sum, item) => sum + item.subtotal_cents,
      0
    );
    const tax_cents = Math.round(subtotal_cents * CONFIG.TAX_RATE);
    const total_cents = subtotal_cents + tax_cents;

    return { subtotal_cents, tax_cents, total_cents };
  };

  const getItemCount = () => {
    return cartItems.reduce((sum, item) => sum + item.quantity, 0);
  };

  const value = {
    cartItems,
    addToCart,
    removeFromCart,
    updateQuantity,
    clearCart,
    calculateTotals,
    getItemCount
  };

  return (
    <CartContext.Provider value={value}>
      {children}
    </CartContext.Provider>
  );
}

export function useCart() {
  const context = useContext(CartContext);
  if (!context) {
    throw new Error('useCart must be used within a CartProvider');
  }
  return context;
}
