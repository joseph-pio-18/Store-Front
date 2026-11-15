import { useEffect, useRef, useState } from 'react'
import './App.css'
import {
  getCustomerBag,
  getLoggedInUser,
  getProducts,
  login,
  logout,
  placeStoreOrder,
  startCustomerRegistration,
  updateCustomerBag,
  verifyCustomerRegistration,
} from './api'

const PRODUCT_CATEGORIES = ['All products', 'Women', 'Men', 'Kids']

function getBagLineKey(productId, variantId) {
  return variantId ? `variant:${variantId}` : `product:${productId}`
}

function getProductImage(product, color) {
  return (
    product.colors?.find((option) => option.color === color)?.image ||
    product.website_image
  )
}

function toBagState(items) {
  return Object.fromEntries(
    items.map(({ product_id, variant_id, color, size, qty, product }) => {
      const lineKey = getBagLineKey(product_id, variant_id)
      return [
        lineKey,
        { lineKey, product_id, variant_id, color, size, product, quantity: qty },
      ]
    }),
  )
}

function getVariantStock(product, variantId) {
  return product?.variants?.find((variant) => variant.variant_id === variantId)?.available_qty
}

function App() {
  const [products, setProducts] = useState([])
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('All products')
  const [selectedProduct, setSelectedProduct] = useState(null)
  const [bag, setBag] = useState({})
  const [bagOpen, setBagOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [account, setAccount] = useState(null)
  const [accountError, setAccountError] = useState('')
  const [authOpen, setAuthOpen] = useState(false)
  const [authMode, setAuthMode] = useState('login')
  const [orderBusy, setOrderBusy] = useState(false)
  const [orderError, setOrderError] = useState('')
  const [orderConfirmation, setOrderConfirmation] = useState(null)
  const [bagReady, setBagReady] = useState(false)
  const [bagBusy, setBagBusy] = useState(false)
  const [bagError, setBagError] = useState('')
  const bagRequestInFlight = useRef(false)

  useEffect(() => {
    let active = true
    getLoggedInUser()
      .then(async (user) => {
        if (!user) {
          if (active) {
            setAccount(null)
            setBag({})
          }
          return
        }

        if (active) setAccount(user)
        const savedBag = await getCustomerBag()
        if (active) setBag(toBagState(savedBag))
      })
      .catch(() => {
        if (active) {
          setBagError('Your saved bag could not be loaded. Refresh the page to try again.')
          setAccountError('Account or bag status could not be checked.')
        }
      })
      .finally(() => {
        if (active) setBagReady(true)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      setLoading(true)
      setError(null)
      getProducts(search, controller.signal, category)
        .then(setProducts)
        .catch((cause) => {
          if (!controller.signal.aborted) {
            setError(cause instanceof Error ? cause.message : 'Could not load products.')
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false)
        })
    }, 200)

    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [search, category])

  const bagItems = Object.values(bag)
  const bagCount = bagItems.reduce((total, item) => total + item.quantity, 0)
  const bagTotal = bagItems.reduce(
    (total, item) => total + (item.product ? item.product.selling_price * item.quantity : 0),
    0,
  )
  const hasUnavailableBagItem = bagItems.some((item) => !item.product)

  async function saveBag(nextBag) {
    if (!account || bagRequestInFlight.current) return false
    bagRequestInFlight.current = true
    setBagBusy(true)
    setBagError('')
    setOrderError('')
    setOrderConfirmation(null)
    try {
      const savedBag = await updateCustomerBag(
        Object.values(nextBag).map((item) => ({
          product_id: item.product_id,
          variant_id: item.variant_id,
          qty: item.quantity,
        })),
      )
      setBag(toBagState(savedBag))
      return true
    } catch (cause) {
      setBagError(cause instanceof Error ? cause.message : 'Your bag could not be saved. Please try again.')
      return false
    } finally {
      bagRequestInFlight.current = false
      setBagBusy(false)
    }
  }

  async function addToBag(product, variant = null) {
    if (!account) {
      setAuthMode('login')
      setAuthOpen(true)
      return false
    }
    const lineKey = getBagLineKey(product.item_code, variant?.variant_id)
    const nextBag = {
      ...bag,
      [lineKey]: {
        lineKey,
        product_id: product.item_code,
        variant_id: variant?.variant_id ?? null,
        color: variant?.color ?? null,
        size: variant?.size ?? null,
        product,
        quantity: (bag[lineKey]?.quantity ?? 0) + 1,
      },
    }
    return saveBag(nextBag)
  }

  function handleProductBagClick(product) {
    if (product.variants?.length) {
      setSelectedProduct(product)
      return
    }
    if (bagItems.some((item) => item.product_id === product.item_code)) {
      setSelectedProduct(null)
      setBagOpen(true)
      return
    }
    addToBag(product)
  }

  function changeBagQuantity(lineKey, quantity) {
    const item = bag[lineKey]
    if (!item || !item.product || quantity < 1 || quantity > 99) return
    const available = getVariantStock(item.product, item.variant_id)
    if (available !== undefined && quantity > available) return
    void saveBag({ ...bag, [lineKey]: { ...item, quantity } })
  }

  function removeFromBag(lineKey) {
    const nextBag = { ...bag }
    delete nextBag[lineKey]
    void saveBag(nextBag)
  }

  async function handlePlaceOrder() {
    if (!account) {
      setAuthMode('login')
      setAuthOpen(true)
      return
    }

    setOrderBusy(true)
    setOrderError('')
    try {
      const order = await placeStoreOrder()
      setBag({})
      setOrderConfirmation(order)
      setBagError('')
    } catch (cause) {
      setOrderError(cause instanceof Error ? cause.message : 'We could not place your order. Please try again.')
    } finally {
      setOrderBusy(false)
    }
  }

  return (
    <main>
      <div className="announcement">
        Complimentary delivery on orders over $100
      </div>

      <header className="site-header">
        <a className="wordmark" href="/" aria-label="Threadform home">
          <span className="wordmark-icon" aria-hidden="true">T</span>
          <span>THREADFORM</span>
        </a>
        <nav className="main-nav" aria-label="Main navigation">
          <a href="#collection">Shop</a>
          <a href="#features">Our approach</a>
          <a href="#story">Our story</a>
        </nav>
        <div className="header-actions">
          {account ? (
            <>
              <span className="account-name" title={account.email}>
                {account.full_name || account.email}
              </span>
              <button
                className="account-button"
                onClick={async () => {
                  try {
                    await logout()
                    setAccount(null)
                    setBag({})
                    setBagReady(true)
                    setBagError('')
                    setAccountError('')
                  } catch (cause) {
                    setAccountError(
                      cause instanceof Error ? cause.message : 'Could not sign out. Please try again.',
                    )
                  }
                }}
                type="button"
              >
                Sign out
              </button>
            </>
          ) : (
            <button
              className="account-button"
              onClick={() => {
                setAuthMode('login')
                setAuthOpen(true)
              }}
              type="button"
            >
              Sign in
            </button>
          )}
          {accountError && <span className="account-error" role="status">{accountError}</span>}
          <button
            aria-controls="bag-panel"
            aria-expanded={bagOpen}
            aria-label={`Bag, ${bagCount} items`}
            className="bag-button"
            onClick={() => setBagOpen((open) => !open)}
            type="button"
          >
            Bag <span>{bagCount}</span>
          </button>
        </div>
      </header>

      <section className="hero" id="story">
        <div className="hero-copy">
          <p className="eyebrow">THE NEW EVERYDAY</p>
          <h1>Quietly<br /><em>considered.</em></h1>
          <p className="hero-description">
            Thoughtful pieces, made to be lived in. Discover effortless
            essentials for women, men, and little ones.
          </p>
          <a className="text-link" href="#collection">Discover the collection <span aria-hidden="true">-&gt;</span></a>
        </div>
        <div className="hero-art" aria-label="Featured clothing from the latest collection" role="group">
          {products.slice(0, 3).map((product, index) => (
            <button
              aria-label={`View ${product.item_name}`}
              className={`hero-product hero-product-${index + 1}`}
              key={product.item_code}
              onClick={() => setSelectedProduct(product)}
              type="button"
            >
              {product.website_image ? (
                <img alt="" src={product.website_image} />
              ) : (
                <span className="hero-product-placeholder">{product.item_name.slice(0, 1)}</span>
              )}
              <span>{product.item_name}</span>
            </button>
          ))}
          {products.length === 0 && (
            <div className="hero-editorial" aria-hidden="true">
              <span className="editorial-shape editorial-shape-one" />
              <span className="editorial-shape editorial-shape-two" />
              <span className="editorial-note">THREADFORM<br />STUDIO / 01</span>
            </div>
          )}
          <div className="hero-art-caption">
            <span>NEW SEASON</span>
            <span>01 — 03</span>
          </div>
        </div>
      </section>

      <section className="features" id="features" aria-label="Our approach">
        <article className="feature">
          <span className="feature-mark" aria-hidden="true">01</span>
          <div><h2>Considered by design</h2><p>Thoughtful details, with nothing extra.</p></div>
        </article>
        <article className="feature">
          <span className="feature-mark" aria-hidden="true">02</span>
          <div><h2>Made for real life</h2><p>Comfort you will reach for, every day.</p></div>
        </article>
        <article className="feature">
          <span className="feature-mark" aria-hidden="true">03</span>
          <div><h2>For every generation</h2><p>Easy pieces for women, men, and kids.</p></div>
        </article>
      </section>

      <section className="collection" id="collection">
        <div className="collection-heading">
          <div>
            <p className="eyebrow">MADE TO BE WORN</p>
            <h2>Everyday <em>favourites.</em></h2>
          </div>
          <p className="collection-note">A little more thoughtful. A lot more you.</p>
        </div>

        <div className="collection-toolbar">
          <div className="category-list" aria-label="Product categories">
            {PRODUCT_CATEGORIES.map((item) => (
              <button
                className={category === item ? 'category-chip active' : 'category-chip'}
                key={item}
                onClick={() => setCategory(item)}
                type="button"
              >
                {item}
              </button>
            ))}
          </div>
          <label className="search-field">
            <span className="search-icon" aria-hidden="true">/</span>
            <span className="visually-hidden">Search products</span>
            <input
              onChange={(event) => {
                setSearch(event.target.value)
                setCategory('All products')
              }}
              placeholder="Search products"
              type="search"
              value={search}
            />
          </label>
        </div>

        {loading && <p className="state-message" role="status">Loading the collection...</p>}
        {!loading && error && (
          <div className="state-message error-message" role="alert">
            <strong>We could not load the collection.</strong>
            <span>{error}</span>
            <span>Check that the Frappe site is running and contains published products.</span>
          </div>
        )}
        {!loading && !error && products.length === 0 && (
          <p className="state-message">
            {search
              ? `No ${category === 'All products' ? 'products' : `${category.toLowerCase()} products`} match that search.`
              : `No ${category === 'All products' ? 'products' : `${category.toLowerCase()} products`} are available yet.`}
          </p>
        )}
        {!loading && !error && products.length > 0 && (
          <div className="product-grid">
            {products.map((product, index) => (
              <article className="product-card" key={product.item_code}>
                <button
                  aria-label={`View ${product.item_name}`}
                  className={`product-image image-tone-${index % 4}`}
                  onClick={() => setSelectedProduct(product)}
                  type="button"
                >
                  {getProductImage(product, product.colors?.[0]?.color) ? (
                    <img alt="" loading="lazy" src={getProductImage(product, product.colors?.[0]?.color)} />
                  ) : (
                    <span className="swatch-placeholder" aria-hidden="true">{product.item_name.slice(0, 1)}</span>
                  )}
                  <span className="image-label">{product.product_category || 'TEXTILE'}</span>
                </button>
                <div className="product-meta">
                  <div>
                    <h3>{product.item_name}</h3>
                    <p>{product.product_category || product.item_code}</p>
                  </div>
                  <p className="product-price">{formatPrice(product.selling_price, product.currency)}</p>
                </div>
                <div className="product-actions">
                  <button className="details-button" onClick={() => setSelectedProduct(product)} type="button">
                    View details
                  </button>
                  <button
                    className="add-button"
                    disabled={!bagReady || bagBusy || Boolean(bagError)}
                    onClick={() => handleProductBagClick(product)}
                    type="button"
                  >
                    {product.variants?.length
                      ? 'Choose options'
                      : bagItems.some((item) => item.product_id === product.item_code)
                        ? 'Go to Bag'
                        : 'Add to Bag'}
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <footer className="site-footer">
        <a className="wordmark" href="/" aria-label="Threadform home">
          <span className="wordmark-icon" aria-hidden="true">T</span>
          <span>THREADFORM</span>
        </a>
        <p>Thoughtful clothing, made for the everyday.</p>
        <span className="footer-note">Made with intention</span>
      </footer>

      {selectedProduct && (
        <ProductDialog
          disabled={!bagReady || bagBusy || Boolean(bagError)}
          onAdd={(variant) => {
            void addToBag(selectedProduct, variant).then((added) => {
              if (added) {
                setSelectedProduct(null)
                setBagOpen(true)
              }
            })
          }}
          onClose={() => setSelectedProduct(null)}
          product={selectedProduct}
        />
      )}
      {authOpen && (
        <AuthDialog
          mode={authMode}
          onAuthenticated={async (user) => {
            setAccount(user)
            setAccountError('')
            setBagBusy(true)
            try {
              const savedBag = await getCustomerBag()
              setBag(toBagState(savedBag))
              setBagError('')
            } catch (cause) {
              setBagError(
                cause instanceof Error ? cause.message : 'Your saved bag could not be loaded.',
              )
            } finally {
              setBagReady(true)
              setBagBusy(false)
              setAuthOpen(false)
            }
          }}
          onClose={() => setAuthOpen(false)}
          onModeChange={setAuthMode}
        />
      )}
      {bagOpen && (
        <div className="bag-backdrop" onMouseDown={() => setBagOpen(false)} role="presentation">
          <aside
            aria-label="Your bag"
            className="bag-panel"
            id="bag-panel"
            onMouseDown={(event) => event.stopPropagation()}
            role="complementary"
          >
            <div className="bag-heading">
              <h2>Your bag <span>({bagCount})</span></h2>
              <button onClick={() => setBagOpen(false)} type="button">Close</button>
            </div>
              {bagError && <p className="order-error" role="alert">{bagError}</p>}
              {!bagReady ? (
                <p className="bag-empty" role="status">Loading your saved bag...</p>
              ) : bagItems.length === 0 ? (
                <div className="bag-empty">
                {orderConfirmation ? (
                  <>
                    <strong>Order placed</strong>
                    <span>Order {orderConfirmation.order_id} is pending confirmation.</span>
                    <span>Expected delivery: {orderConfirmation.expected_delivery_date}</span>
                    <span>Order details were sent to {account?.email}.</span>
                    <span>Payment has not been collected.</span>
                  </>
                ) : (
                  <span>Your bag is ready for something special.</span>
                )}
              </div>
            ) : (
              <ul className="bag-list">
                {bagItems.map(({ product, product_id, variant_id, color, size, quantity, lineKey }) => (
                  <li key={lineKey}>
                    <div className="bag-product">
                      {product && getProductImage(product, color) ? (
                        <img alt="" className="bag-product-image" src={getProductImage(product, color)} />
                      ) : (
                        <span className="bag-product-placeholder" aria-hidden="true">
                          {product?.item_name?.slice(0, 1) || '?'}
                        </span>
                      )}
                      <div className="bag-product-details">
                        <strong>{product?.item_name || product_id}</strong>
                        {(color || size) && (
                          <span>{[color, size].filter(Boolean).join(' · ')}</span>
                        )}
                        {product ? (
                          <span>{formatPrice(product.selling_price, product.currency)} each</span>
                        ) : (
                          <span className="unavailable-item">No longer available</span>
                        )}
                        <div className="quantity-control" aria-label={`Quantity for ${product?.item_name || product_id}`}>
                          <button
                            aria-label={`Decrease ${product?.item_name || product_id} quantity`}
                            disabled={!product || quantity <= 1 || bagBusy}
                            onClick={() => changeBagQuantity(lineKey, quantity - 1)}
                            type="button"
                          >
                            -
                          </button>
                          <span>{quantity}</span>
                          <button
                            aria-label={`Increase ${product?.item_name || product_id} quantity`}
                            disabled={
                              !product ||
                              quantity >= 99 ||
                              bagBusy ||
                              (getVariantStock(product, variant_id) !== undefined &&
                                quantity >= getVariantStock(product, variant_id))
                            }
                            onClick={() => changeBagQuantity(lineKey, quantity + 1)}
                            type="button"
                          >
                            +
                          </button>
                        </div>
                        <button
                          className="remove-item-button"
                          disabled={bagBusy}
                          onClick={() => removeFromBag(lineKey)}
                          type="button"
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                    <strong className="bag-line-total">
                      {product
                        ? formatPrice(product.selling_price * quantity, product.currency)
                        : '—'}
                    </strong>
                  </li>
                ))}
              </ul>
            )}
            {orderError && <p className="order-error" role="alert">{orderError}</p>}
            <div className="bag-total">
              <span>Subtotal</span>
              <strong>{formatPrice(bagTotal, bagItems[0]?.product?.currency ?? null)}</strong>
            </div>
            <button
              className="checkout-button"
              disabled={!bagItems.length || orderBusy || bagBusy || !bagReady || hasUnavailableBagItem}
              onClick={handlePlaceOrder}
              type="button"
            >
              {orderBusy ? 'Placing order...' : account ? 'Place order' : 'Sign in to place order'}
            </button>
            <p className="bag-note">
              Orders are recorded as pending requests. Variant quantities are reserved until staff cancel the order; payment is not collected online.
            </p>
          </aside>
        </div>
      )}
    </main>
  )
}

function ProductDialog({
  disabled,
  onAdd,
  onClose,
  product,
}) {
  const colors = product.colors ?? []
  const variants = product.variants ?? []
  const [selectedColor, setSelectedColor] = useState(colors[0]?.color ?? '')
  const [selectedSize, setSelectedSize] = useState('')

  useEffect(() => {
    const firstAvailable = variants.find((variant) => variant.available_qty > 0)
    if (firstAvailable) {
      setSelectedColor(firstAvailable.color)
      setSelectedSize(firstAvailable.size)
    }
  }, [product.item_code])

  useEffect(() => {
    function closeOnEscape(event) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  const colorVariants = variants.filter((variant) => variant.color === selectedColor)
  const selectedVariant = colorVariants.find((variant) => variant.size === selectedSize)
  const image = getProductImage(product, selectedColor)
  const standardSizeOrder = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']
  const sizes = [...new Set(colorVariants.map((variant) => variant.size))].sort((a, b) => {
    const aIndex = standardSizeOrder.indexOf(a.toUpperCase())
    const bIndex = standardSizeOrder.indexOf(b.toUpperCase())
    if (aIndex >= 0 || bIndex >= 0) {
      return (aIndex < 0 ? standardSizeOrder.length : aIndex) -
        (bIndex < 0 ? standardSizeOrder.length : bIndex)
    }
    return a.localeCompare(b)
  })

  return (
    <div className="dialog-backdrop" onMouseDown={onClose} role="presentation">
      <section
        aria-labelledby="product-dialog-title"
        aria-modal="true"
        className="product-dialog"
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
      >
        <button aria-label="Close product details" className="dialog-close" onClick={onClose} type="button">
          Close
        </button>
        <div className="dialog-image">
          {image ? (
            <img alt="" src={image} />
          ) : (
            <span className="swatch-placeholder" aria-hidden="true">{product.item_name.slice(0, 1)}</span>
          )}
        </div>
        <div className="dialog-copy">
          <p className="eyebrow">{product.product_category || 'TEXTILE'}</p>
          <h2 id="product-dialog-title">{product.item_name}</h2>
          <p className="dialog-description">
            {product.website_description || 'A thoughtfully made textile, ready for your next project.'}
          </p>
          <p className="dialog-unit">Sold by {product.stock_uom}</p>
          <p className="dialog-price">{formatPrice(product.selling_price, product.currency)}</p>
          {variants.length > 0 && (
            <div className="variant-picker">
              <div>
                <p className="variant-label">Color <strong>{selectedColor}</strong></p>
                <div className="variant-options">
                  {colors.map((option) => (
                    <button
                      aria-pressed={selectedColor === option.color}
                      className={selectedColor === option.color ? 'variant-option active' : 'variant-option'}
                      key={option.color}
                      onClick={() => {
                        setSelectedColor(option.color)
                        const firstSize = variants.find(
                          (variant) => variant.color === option.color && variant.available_qty > 0,
                        )
                        setSelectedSize(firstSize?.size ?? '')
                      }}
                      type="button"
                    >
                      {option.color}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <p className="variant-label">Size</p>
                <div className="variant-options">
                  {sizes.map((size) => {
                    const variant = colorVariants.find((option) => option.size === size)
                    const available = variant?.available_qty > 0
                    return (
                      <button
                        aria-pressed={selectedSize === size}
                        className={selectedSize === size ? 'variant-option active' : 'variant-option'}
                        disabled={!available}
                        key={size}
                        onClick={() => setSelectedSize(size)}
                        type="button"
                      >
                        {size}{available ? ` · ${variant.available_qty} available` : ' · Sold out'}
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>
          )}
          <button
            className="add-button dialog-add"
            disabled={
              disabled ||
              (variants.length > 0 && (!selectedVariant || selectedVariant.available_qty < 1))
            }
            onClick={() => onAdd(selectedVariant ?? null)}
            type="button"
          >
            Add to Bag
          </button>
          <p className="dialog-footnote">Orders are recorded as pending requests; selected variant quantities are reserved when placed. Payment is not collected online.</p>
        </div>
      </section>
    </div>
  )
}

function formatPrice(amount, currency) {
  if (currency && /^[A-Z]{3}$/.test(currency)) {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(amount)
  }
  return `${amount.toFixed(2)}`
}

function AuthDialog({ mode, onAuthenticated, onClose, onModeChange }) {
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [otp, setOtp] = useState('')
  const [verificationSent, setVerificationSent] = useState(false)
  const [accountExists, setAccountExists] = useState(false)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    function closeOnEscape(event) {
      if (event.key === 'Escape' && !busy) onClose()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [busy, onClose])

  async function handleSubmit(event) {
    event.preventDefault()
    setBusy(true)
    setMessage('')

    try {
      if (mode === 'register') {
        if (password !== confirmPassword) {
          setMessage('Passwords do not match.')
          return
        }
        if (!verificationSent) {
          const result = await startCustomerRegistration({ email, fullName })
          if (result.account_exists) {
            setAccountExists(true)
            return
          }
          setVerificationSent(true)
          setMessage(`We sent a 6-digit verification code to ${email.trim()}.`)
          return
        }
        await verifyCustomerRegistration({
          email,
          otp,
          fullName,
          password,
          confirmPassword,
        })
      }
      const user = await login(email, password)
      await onAuthenticated(user)
    } catch (cause) {
      if (
        mode === 'register' &&
        cause instanceof Error &&
        cause.message.toLowerCase().includes('account with this email already exists')
      ) {
        setAccountExists(true)
      } else {
        setMessage(
          cause instanceof Error
            ? cause.message
            : 'We could not complete your request. Please try again.',
        )
      }
    } finally {
      setBusy(false)
    }
  }

  async function resendVerificationCode() {
    setBusy(true)
    setMessage('')
    try {
      const result = await startCustomerRegistration({ email, fullName })
      if (result.account_exists) {
        setAccountExists(true)
        return
      }
      setOtp('')
      setMessage(`A new verification code was sent to ${email.trim()}.`)
    } catch (cause) {
      setMessage(
        cause instanceof Error
          ? cause.message
          : 'We could not send a new verification code. Please try again.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="dialog-backdrop auth-backdrop" onMouseDown={onClose} role="presentation">
      <section
        aria-labelledby="auth-dialog-title"
        aria-modal="true"
        className="auth-dialog"
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
      >
        {accountExists && (
          <div className="account-exists-backdrop">
            <section
              aria-labelledby="account-exists-title"
              aria-modal="true"
              className="account-exists-dialog"
              role="alertdialog"
            >
              <p className="eyebrow">ACCOUNT FOUND</p>
              <h3 id="account-exists-title">This email is already registered.</h3>
              <p>Sign in with the existing account, or use a different email address.</p>
              <div className="account-exists-actions">
                <button
                  className="details-button"
                  onClick={() => setAccountExists(false)}
                  type="button"
                >
                  Use another email
                </button>
                <button
                  className="add-button"
                  onClick={() => {
                    setAccountExists(false)
                    setVerificationSent(false)
                    setOtp('')
                    setPassword('')
                    setConfirmPassword('')
                    setMessage('')
                    onModeChange('login')
                  }}
                  type="button"
                >
                  Sign in
                </button>
              </div>
            </section>
          </div>
        )}
        <button aria-label="Close account dialog" className="dialog-close" onClick={onClose} type="button">
          Close
        </button>
        <p className="eyebrow">{mode === 'register' ? 'JOIN THREADFORM' : 'WELCOME BACK'}</p>
        <h2 id="auth-dialog-title">{mode === 'register' ? 'Create your account.' : 'Sign in to your account.'}</h2>
        <p className="auth-intro">
          Your account is securely managed by the textile ERP.
        </p>
        <form className="auth-form" onSubmit={handleSubmit}>
          {mode === 'register' && (
            <label>
              Full name
              <input
                autoComplete="name"
                maxLength={140}
                onChange={(event) => setFullName(event.target.value)}
                required
                value={fullName}
              />
            </label>
          )}
          <label>
            Email
            <input
              autoComplete="email"
              maxLength={140}
              onChange={(event) => setEmail(event.target.value)}
              readOnly={mode === 'register' && verificationSent}
              required
              type="email"
              value={email}
            />
          </label>
          <label>
            Password
            <input
              autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
              maxLength={128}
              minLength={mode === 'register' ? 10 : 1}
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
            {mode === 'register' && <span className="field-hint">Use at least 10 characters.</span>}
          </label>
          {mode === 'register' && (
            <label>
              Confirm password
              <input
                autoComplete="new-password"
                maxLength={128}
                minLength={10}
                onChange={(event) => setConfirmPassword(event.target.value)}
                required
                type="password"
                value={confirmPassword}
              />
            </label>
          )}
          {mode === 'register' && verificationSent && (
            <>
              <label>
                Email verification code
                <input
                  autoComplete="one-time-code"
                  inputMode="numeric"
                  maxLength={6}
                  onChange={(event) => setOtp(event.target.value.replace(/\D/g, ''))}
                  pattern="[0-9]{6}"
                  required
                  value={otp}
                />
                <span className="field-hint">Enter the 6-digit code. It expires in 10 minutes.</span>
              </label>
              <div className="auth-verification-actions">
                <button
                  className="auth-resend"
                  disabled={busy}
                  onClick={() => void resendVerificationCode()}
                  type="button"
                >
                  Resend code
                </button>
                <button
                  className="auth-resend"
                  disabled={busy}
                  onClick={() => {
                    setVerificationSent(false)
                    setOtp('')
                    setMessage('')
                  }}
                  type="button"
                >
                  Change email address
                </button>
              </div>
            </>
          )}
          {message && <p className="auth-message" role="alert">{message}</p>}
          <button className="add-button auth-submit" disabled={busy} type="submit">
            {busy
              ? 'Please wait...'
              : mode === 'register'
                ? verificationSent ? 'Verify code & create account' : 'Send verification code'
                : 'Sign in'}
          </button>
        </form>
        <p className="auth-switch">
          {mode === 'register' ? 'Already have an account?' : 'New to Threadform?'}
          {' '}
          <button
            disabled={busy}
            onClick={() => {
              setMessage('')
              onModeChange(mode === 'register' ? 'login' : 'register')
            }}
            type="button"
          >
            {mode === 'register' ? 'Sign in' : 'Create an account'}
          </button>
        </p>
      </section>
    </div>
  )
}

export default App
