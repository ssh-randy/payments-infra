# Frontend Demo - Online Ordering System

A React-based frontend demo application for the payment infrastructure system. This application demonstrates a complete online ordering flow with payment processing.

## Technology Stack

- **Framework**: React 18
- **Build Tool**: Vite
- **Styling**: CSS (inline styles)
- **State Management**: React hooks (useState, useContext)
- **Routing**: React Router
- **HTTP Client**: fetch API

## Project Structure

```
frontend/
├── public/                 # Static assets
│   └── images/            # Image files
├── src/
│   ├── components/        # Reusable UI components
│   │   ├── Header.jsx
│   │   ├── Footer.jsx
│   │   ├── MenuItem.jsx
│   │   ├── Cart.jsx
│   │   └── LoadingSpinner.jsx
│   ├── pages/             # Page components
│   │   ├── MenuPage.jsx
│   │   ├── CheckoutPage.jsx
│   │   └── StatusPage.jsx
│   ├── services/          # API and encryption services
│   │   ├── api.js
│   │   └── encryption.js
│   ├── utils/             # Utility functions
│   │   ├── formatters.js
│   │   └── validators.js
│   ├── context/           # React context providers
│   │   └── CartContext.jsx
│   ├── config/            # Configuration
│   │   └── config.js
│   ├── App.jsx            # Main app component with routing
│   ├── App.css            # Global styles
│   └── main.jsx           # Entry point
├── Dockerfile             # Multi-stage Docker build
├── nginx.conf             # Nginx configuration for production
├── vite.config.js         # Vite configuration
└── package.json           # Dependencies
```

## Development Setup

### Prerequisites

- Node.js 18 or higher
- npm or yarn

### Installation

1. Install dependencies:

```bash
npm install
```

2. Start the development server:

```bash
npm run dev
```

The application will be available at `http://localhost:3000`

### Development Features

- Hot Module Replacement (HMR)
- Fast refresh
- Development server on port 3000

## Building for Production

### Build the application:

```bash
npm run build
```

The production-ready files will be in the `dist/` directory.

### Preview the production build:

```bash
npm run preview
```

## Running with Docker

### Build the Docker image:

```bash
docker build -t payments-frontend .
```

### Run the container:

```bash
docker run -p 3000:80 payments-frontend
```

The application will be available at `http://localhost:3000`

### With environment variables:

```bash
docker run -p 3000:80 \
  -e VITE_PAYMENT_TOKEN_SERVICE_URL=http://payment-token-service:8001 \
  -e VITE_AUTHORIZATION_API_URL=http://authorization-api:8002 \
  payments-frontend
```

## Configuration

Configuration is managed in `src/config/config.js`. You can override settings using environment variables:

- `VITE_PAYMENT_TOKEN_SERVICE_URL` - Payment Token Service URL (default: `http://localhost:8001`)
- `VITE_AUTHORIZATION_API_URL` - Authorization API URL (default: `http://localhost:8002`)

## Application Flow

1. **Menu Page** (`/`)
   - Browse menu items
   - Add items to cart
   - View cart summary
   - Proceed to checkout

2. **Checkout Page** (`/checkout`)
   - Enter payment information
   - Submit payment
   - Process payment through backend services

3. **Status Page** (`/status`)
   - Poll payment status
   - Display payment result
   - Return to menu

## Test Card Numbers

Use these test card numbers for testing:

- **Success**: `4242 4242 4242 4242`
- **Declined**: `4000 0000 0000 0002`
- **Insufficient Funds**: `4000 0000 0000 9995`
- **Expired Card**: `4000 0000 0000 0069`

For testing:
- Use any future expiration date (e.g., `12/2025`)
- Use any 3-digit CVV (e.g., `123`)
- Use any email address

## API Services

The frontend communicates with the following backend services:

1. **Payment Token Service** (port 8001)
   - Create payment tokens from card details
   - Encrypt sensitive card data

2. **Authorization API** (port 8002)
   - Authorize payments
   - Poll payment status
   - Communicate with Stripe

## Development Notes

### Current Implementation Status

This is the foundational setup with:
- ✅ Basic project structure
- ✅ Page components with placeholder content
- ✅ Routing setup
- ✅ API service stubs
- ✅ Utility functions for validation and formatting
- ✅ Docker setup with nginx

### Upcoming Implementations

- **i-3oa3**: Menu rendering with real menu data
- **i-82kx**: Payment token creation with encryption
- **i-5xjm**: Payment authorization and status polling

## Browser Support

- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)

## Security

- All payment processing happens server-side
- Card details are encrypted before transmission
- No sensitive data is stored in the frontend
- Security headers configured in nginx

## Troubleshooting

### Port already in use

If port 3000 is already in use, you can change it in `vite.config.js`:

```javascript
server: {
  port: 3001, // Change to another port
  host: true
}
```

### Build errors

Clear the node_modules and reinstall:

```bash
rm -rf node_modules package-lock.json
npm install
```

## Links

- [Vite Documentation](https://vitejs.dev/)
- [React Documentation](https://react.dev/)
- [React Router Documentation](https://reactrouter.com/)

## License

Proprietary - Demo Application
