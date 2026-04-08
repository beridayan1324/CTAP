import React, { useRef, useMemo } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { useNavigate } from 'react-router-dom';

const FloatingDataParticles = ({ count = 2000 }) => {
    const mesh = useRef();
    
    const particles = useMemo(() => {
        const temp = new Float32Array(count * 3);
        const radius = 15;
        for (let i = 0; i < count; i++) {
            const theta = Math.random() * 2 * Math.PI;
            const phi = Math.acos((Math.random() * 2) - 1);
            const r = radius * Math.cbrt(Math.random());

            temp[i * 3] = r * Math.sin(phi) * Math.cos(theta);
            temp[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
            temp[i * 3 + 2] = r * Math.cos(phi);
        }
        return temp;
    }, [count]);

    useFrame((state, delta) => {
        if (mesh.current) {
            mesh.current.rotation.y += delta * 0.05;
            mesh.current.rotation.x += delta * 0.02;
        }
    });

    return (
        <points ref={mesh}>
            <bufferGeometry>
                <bufferAttribute
                    attach="attributes-position"
                    count={particles.length / 3}
                    array={particles}
                    itemSize={3}
                />
            </bufferGeometry>
            <pointsMaterial size={0.03} color="#ffffff" transparent opacity={0.6} sizeAttenuation />
        </points>
    );
};

const Landing = () => {
    const navigate = useNavigate();

    return (
        <div style={{ position: 'relative', width: '100vw', height: '100vh', overflow: 'hidden', background: '#030303' }}>
            <div style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', zIndex: 0 }}>
                <Canvas camera={{ position: [0, 0, 10], fov: 60 }}>
                    <fog attach="fog" color="#030303" near={5} far={15} />
                    <FloatingDataParticles />
                </Canvas>
            </div>
            
            <div style={{ 
                position: 'absolute', 
                top: 0, 
                left: 0, 
                width: '100%', 
                height: '100%', 
                zIndex: 1,
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
                alignItems: 'center',
                pointerEvents: 'none'
            }}>
                <div style={{ textAlign: 'center', mixBlendMode: 'difference' }}>
                    <h1 style={{ 
                        fontFamily: 'var(--font-sans)', 
                        fontSize: '5rem', 
                        fontWeight: 600,
                        letterSpacing: '-0.05em',
                        marginBottom: '1rem'
                    }}>
                        CTAP Chat
                    </h1>
                    <p style={{ 
                        fontFamily: 'var(--font-mono)', 
                        fontSize: '0.9rem',
                        textTransform: 'uppercase',
                        letterSpacing: '0.2em',
                        opacity: 0.7,
                        marginBottom: '3rem'
                    }}>
                        Secure Hardware & Web Chat System
                    </p>
                    <button 
                        style={{ pointerEvents: 'auto', padding: '16px 32px' }}
                        onClick={() => navigate('/login')}
                    >
                        Log In
                    </button>
                </div>
            </div>
        </div>
    );
};

export default Landing;
