import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useCart } from '../context/CartContext';
import Header from '../components/Header';
import Footer from '../components/Footer';
import MenuItem from '../components/MenuItem';
import Cart from '../components/Cart';
import { MOCK_MENU_ITEMS, groupByCategory } from '../data/menuData';

/**
 * MenuPage - Menu browsing and cart page
 * Displays menu items grouped by category with cart management
 */
function MenuPage() {
  const navigate = useNavigate();
  const { addToCart, cartItems } = useCart();

  // Group menu items by category
  const categorizedMenu = groupByCategory(MOCK_MENU_ITEMS);

  const handleAddToCart = (item) => {
    addToCart(item);
  };

  const handleCheckout = () => {
    if (cartItems.length === 0) {
      alert('Please add items to your cart first!');
      return;
    }
    navigate('/checkout');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', backgroundColor: '#f5f5f5' }}>
      <Header />

      <main style={{
        flex: 1,
        maxWidth: '1400px',
        width: '100%',
        margin: '0 auto',
        padding: '2rem',
        display: 'grid',
        gridTemplateColumns: '1fr 380px',
        gap: '2rem'
      }}>
        <div>
          <h1 style={{ marginTop: 0, marginBottom: '0.5rem', color: '#2c3e50' }}>Our Menu</h1>
          <p style={{ color: '#666', marginBottom: '2rem' }}>
            Browse our delicious selection and add items to your cart
          </p>

          {Object.entries(categorizedMenu).map(([category, items]) => (
            <div key={category} style={{ marginBottom: '2.5rem' }}>
              <h2 style={{
                fontSize: '1.5rem',
                color: '#34495e',
                marginBottom: '1rem',
                paddingBottom: '0.5rem',
                borderBottom: '2px solid #3498db'
              }}>
                {category}
              </h2>
              <div>
                {items.map(item => (
                  <MenuItem
                    key={item.id}
                    item={item}
                    onAddToCart={handleAddToCart}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>

        <div>
          <Cart onCheckout={handleCheckout} />
        </div>
      </main>

      <Footer />
    </div>
  );
}

export default MenuPage;
