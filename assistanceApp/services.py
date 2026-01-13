import json
from typing import Dict, List, Optional
from django.conf import settings
import time
import random
from sentence_transformers import SentenceTransformer, util
import torch
import uuid
import time
import uuid
from datetime import timedelta
from django.db import models
from django.utils import timezone
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

from .models import FAQ, AssistanceChat, AssistanceMessage, AIResponseLog


class FreeAIService:
    """FREE AI service using local models - no API key needed!"""
    
    def __init__(self):
        print("🚀 Initializing FREE AI Service...")
        
        try:
            # Load a small, fast embedding model for FAQ matching
            print("📥 Loading embedding model...")
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            print("✅ Embedding model loaded!")
            
            # Load FAQ embeddings
            self.faq_embeddings = None
            self.faq_data = []
            self._load_faq_embeddings()
            
        except Exception as e:
            print(f"⚠️ Could not load models: {e}")
            print("📝 Using rule-based fallback system")
            self.embedding_model = None
    
    def _load_faq_embeddings(self):
        """Load and embed all FAQs"""
        try:
            faqs = FAQ.objects.filter(is_active=True)
            self.faq_data = []
            faq_texts = []
            
            for faq in faqs:
                self.faq_data.append({
                    'id': faq.id,
                    'question': faq.question,
                    'answer': faq.answer,
                    'keywords': faq.keywords
                })
                # Combine question and keywords for better matching
                faq_texts.append(f"{faq.question} {faq.keywords}")
            
            if faq_texts and self.embedding_model:
                self.faq_embeddings = self.embedding_model.encode(faq_texts, convert_to_tensor=True)
                print(f"✅ Loaded embeddings for {len(faq_texts)} FAQs")
            else:
                print("ℹ️ No FAQs found or model not loaded")
                
        except Exception as e:
            print(f"❌ Error loading FAQ embeddings: {e}")
    
    def generate_response(self, user_query: str, chat_context: List[Dict] = None) -> Dict:
        """
        Generate AI response using FREE local models
        """
        start_time = time.time()
        
        try:
            # 1. Try FAQ matching first
            faq_match = self._match_faq(user_query)
            if faq_match and faq_match['confidence'] > 0.6:
                print(f"✅ FAQ match found (confidence: {faq_match['confidence']:.2f})")
                return {
                    'response': faq_match['answer'],
                    'confidence': faq_match['confidence'],
                    'faq_id': faq_match['id'],
                    'source': 'faq'
                }
            
            # 2. Use rule-based responses for common questions
            rule_response = self._rule_based_response(user_query)
            if rule_response:
                print(f"✅ Rule-based response found")
                return {
                    'response': rule_response['answer'],
                    'confidence': rule_response['confidence'],
                    'faq_id': None,
                    'source': 'rules'
                }
            
            # 3. Generate template-based response
            response = self._template_response(user_query, chat_context)
            response_time = time.time() - start_time
            
            print(f"✅ Generated response in {response_time:.2f}s")
            
            return {
                'response': response,
                'confidence': 0.7,
                'faq_id': None,
                'source': 'template',
                'response_time': response_time
            }
            
        except Exception as e:
            print(f"❌ AI service error: {str(e)}")
            return self._fallback_response(user_query)
    
    def _match_faq(self, user_query: str) -> Optional[Dict]:
        """Match user query with FAQs using embeddings"""
        try:
            if not self.embedding_model or not self.faq_embeddings:
                return self._simple_faq_match(user_query)
            
            # Encode user query
            query_embedding = self.embedding_model.encode(user_query, convert_to_tensor=True)
            
            # Calculate similarity with all FAQs
            similarities = util.cos_sim(query_embedding, self.faq_embeddings)[0]
            
            # Find best match
            best_score, best_idx = torch.max(similarities, dim=0)
            best_score = best_score.item()
            
            if best_score > 0.4:  # Good match threshold
                faq = self.faq_data[best_idx]
                
                # Update FAQ counter
                try:
                    faq_obj = FAQ.objects.get(id=faq['id'])
                    faq_obj.times_asked += 1
                    faq_obj.save()
                except:
                    pass
                
                return {
                    'id': faq['id'],
                    'answer': faq['answer'],
                    'confidence': best_score
                }
            
        except Exception as e:
            print(f"FAQ matching error: {e}")
        
        return None
    
    def _simple_faq_match(self, user_query: str) -> Optional[Dict]:
        """Simple keyword-based FAQ matching"""
        try:
            user_query_lower = user_query.lower()
            faqs = FAQ.objects.filter(is_active=True)
            
            for faq in faqs:
                # Check keywords
                keywords = [k.strip().lower() for k in faq.keywords.split(',')]
                for keyword in keywords:
                    if keyword and keyword in user_query_lower:
                        faq.times_asked += 1
                        faq.save()
                        return {
                            'id': faq.id,
                            'answer': faq.answer,
                            'confidence': 0.8
                        }
                
                # Check question words
                question_words = set(faq.question.lower().split()[:10])
                query_words = set(user_query_lower.split())
                common_words = question_words.intersection(query_words)
                
                if len(common_words) >= 2:
                    faq.times_asked += 1
                    faq.save()
                    return {
                        'id': faq.id,
                        'answer': faq.answer,
                        'confidence': 0.6
                    }
            
        except Exception as e:
            print(f"Simple FAQ error: {e}")
        
        return None
    
    def _rule_based_response(self, user_query: str) -> Optional[Dict]:
        """Rule-based responses for common questions"""
        user_query_lower = user_query.lower()
        
        # Define rules for common questions
        rules = [
            {
                'keywords': ['hello', 'hi', 'hey', 'greetings'],
                'response': "Hello! Welcome to Digital Mentorship Platform. How can I assist you today?",
                'confidence': 0.9
            },
            {
                'keywords': ['thank', 'thanks', 'appreciate'],
                'response': "You're welcome! Is there anything else I can help you with?",
                'confidence': 0.9
            },
            {
                'keywords': ['password', 'reset password', 'forgot password'],
                'response': "To reset your password, click 'Forgot Password' on the login page. You'll receive an email with reset instructions.",
                'confidence': 0.85
            },
            {
                'keywords': ['create account', 'sign up', 'register'],
                'response': "To create an account, visit our registration page and enter your details. You'll need a valid email address.",
                'confidence': 0.85
            },
            {
                'keywords': ['mentor', 'become mentor', 'apply mentor'],
                'response': "To become a mentor, complete your profile and apply through the mentorship section. Our team will review your experience.",
                'confidence': 0.85
            },
            {
                'keywords': ['mentee', 'find mentor', 'need mentor'],
                'response': "As a mentee, you'll be matched with suitable mentors based on your goals and interests. Complete your profile to get started.",
                'confidence': 0.85
            },
            {
                'keywords': ['contact', 'support', 'help', 'email'],
                'response': "For support, email support@digital-mentorship.com or use the contact form on our website.",
                'confidence': 0.85
            },
            {
                'keywords': ['feature', 'what can', 'platform do'],
                'response': "Our platform offers mentorship matching, progress tracking, video calls, chat, and resource sharing between mentors and mentees.",
                'confidence': 0.8
            },
        ]
        
        # Check each rule
        for rule in rules:
            for keyword in rule['keywords']:
                if keyword in user_query_lower:
                    return {
                        'answer': rule['response'],
                        'confidence': rule['confidence']
                    }
        
        return None
    
    def _template_response(self, user_query: str, chat_context: List[Dict] = None) -> str:
        """Generate template-based response with context awareness"""
        
        # Extract main topic
        words = user_query.lower().split()
        topic = ' '.join(words[:min(5, len(words))])
        
        # Check if this is a follow-up question
        is_follow_up = False
        if chat_context and len(chat_context) > 1:
            is_follow_up = True
        
        if is_follow_up:
            templates = [
                "Continuing from our previous conversation about '{topic}', I understand you're looking for more information. Could you provide additional details about what specifically you need help with?",
                
                "Regarding your follow-up question about '{topic}', I want to make sure I give you the most accurate information. Could you clarify what aspect you're most interested in?",
                
                "I see you're asking more about '{topic}'. To help you better, could you provide more context or let me know if there's a specific problem you're trying to solve?"
            ]
        else:
            # Categorize the query
            if any(word in user_query.lower() for word in ['how', 'what', 'when', 'where', 'why', 'can']):
                # Question-type query
                templates = [
                    "Based on your question about '{topic}', here's what I can tell you: Our mentorship platform is designed to connect mentors and mentees effectively. For specific details related to your situation, please provide more context.",
                    
                    "Regarding '{topic}', our platform offers several features that might help. Could you provide more details about what you're looking to achieve?",
                    
                    "I understand you're asking about '{topic}'. The best way to assist you is to understand your specific needs. Could you share more about what you're hoping to accomplish?"
                ]
            else:
                # Statement-type query
                templates = [
                    "Thank you for sharing about '{topic}'. Our mentorship platform can help with that. For personalized assistance, could you tell me more about your goals?",
                    
                    "I see you mentioned '{topic}'. Our team can provide detailed guidance on this. Would you like to share more about your specific situation?",
                    
                    "Regarding '{topic}', we have resources available. To connect you with the right information, could you please provide more details about what you need?"
                ]
        
        # Select random template
        template = random.choice(templates)
        response = template.format(topic=topic)
        
        return response
    
    def _fallback_response(self, user_query: str) -> Dict:
        """Fallback response when AI can't generate a good answer"""
        fallbacks = [
            "I understand you need assistance with mentorship. For detailed help, could you please provide your email address so our team can contact you?",
            "Thank you for reaching out. To ensure you get accurate information, please share your email address for follow-up.",
            "I want to provide you with the best assistance. Could you please provide your email address so we can help you properly?"
        ]
        
        return {
            'response': random.choice(fallbacks),
            'confidence': 0.3,
            'faq_id': None,
            'source': 'fallback',
            'response_time': 0.1
        }


class EmailService:
    """Service for sending professional email responses"""
    
    def __init__(self):
        self.from_email = getattr(settings, 'ASSISTANCE_FROM_EMAIL', settings.DEFAULT_FROM_EMAIL)
    
    def send_assistance_response(self, chat_session, response_content, responder=None):
        """
        Send assistance response via email
        """
        from django.core.mail import EmailMultiAlternatives
        from django.template.loader import render_to_string
        
        # Get recipient email
        recipient_email = chat_session.get_user_email()
        
        if not recipient_email:
            print(f"❌ No email available for session {chat_session.session_id}")
            return False
        
        # Get the user's question
        user_question = chat_session.messages.filter(
            message_type='user_question'
        ).last()
        
        if not user_question:
            user_question_text = "Your question"
        else:
            user_question_text = user_question.content
        
        # Prepare email content
        context = {
            'user_name': chat_session.user.full_name if chat_session.user else 'Valued User',
            'question': user_question_text,
            'response': response_content,
            'responder_name': responder.full_name if responder else 'Digital Mentorship Team',
            'responder_role': responder.role if responder else 'Support Team',
            'response_date': time.strftime('%B %d, %Y'),
            'tracking_id': str(uuid.uuid4())[:8].upper(),
            'platform_url': settings.FRONTEND_URL,
        }
        
        # Render email templates
        subject = f"Response to your question - Digital Mentorship Assistance #{context['tracking_id']}"
        
        # Try to render templates, fallback to simple text
        try:
            text_content = render_to_string('assistance/email_response.txt', context)
            html_content = render_to_string('assistance/email_response.html', context)
        except:
            # Fallback if templates don't exist
            text_content = f"""Digital Mentorship Platform - Response to Your Question

Hello {context['user_name']},

Thank you for your question: "{context['question'][:100]}"

Here's our response:
{response_content}

Best regards,
{context['responder_name']}
{context['responder_role']}
Digital Mentorship Team

Reference ID: {context['tracking_id']}
"""
            html_content = f"""
<!DOCTYPE html>
<html>
<body>
<h2>Digital Mentorship Platform - Response to Your Question</h2>
<p>Hello {context['user_name']},</p>
<p>Thank you for your question: "{context['question'][:100]}"</p>
<p>Here's our response:</p>
<div style="background:#f5f5f5; padding:15px; border-left:4px solid #667eea;">
{response_content.replace('\n', '<br>')}
</div>
<p>Best regards,<br>
{context['responder_name']}<br>
{context['responder_role']}<br>
Digital Mentorship Team</p>
<p><small>Reference ID: {context['tracking_id']}</small></p>
</body>
</html>
"""
        
        # Send email
        try:
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=self.from_email,
                to=[recipient_email],
                reply_to=[self.from_email]
            )
            email.attach_alternative(html_content, "text/html")
            
            email.send(fail_silently=False)
            
            # Save email record
            from .models import EmailResponse
            EmailResponse.objects.create(
                chat=chat_session,
                subject=subject,
                body=html_content,
                sent_to=recipient_email,
                is_sent=True,
                sent_by=responder,
                tracking_id=context['tracking_id']
            )
            
            print(f"✅ Email sent to {recipient_email}")
            return True
            
        except Exception as e:
            print(f"❌ Email sending failed: {e}")
            
            # Save failed attempt
            from .models import EmailResponse
            EmailResponse.objects.create(
                chat=chat_session,
                subject=subject,
                body=html_content,
                sent_to=recipient_email,
                is_sent=False,
                sent_by=responder
            )
            
            return False


class AssistanceManager:
    """Enhanced manager for AI assistance system with session linking"""
    
    def __init__(self):
        self.ai_service = FreeAIService()
        self.email_service = EmailService()
        self.faq_cache = None
        self.faq_last_update = None
        self.similarity_threshold = 0.65
        self.confidence_threshold = 0.4
        print("✅ Enhanced Assistance Manager initialized")
    
    def create_chat_session(self, request, email=None):
        """Create a new assistance chat session"""
        import uuid
        
        session_id = f"assist_{uuid.uuid4().hex[:8]}"
        
        # Get user info
        user = request.user if request.user.is_authenticated else None
        
        # Get IP and user agent
        ip_address = self._get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        # Create anonymous token for unauthenticated users
        anonymous_token = None
        if not user:
            anonymous_token = f"anon_{uuid.uuid4().hex[:12]}"
        
        chat_session = AssistanceChat.objects.create(
            user=user,
            session_id=session_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            status='ai_handled',
            anonymous_token=anonymous_token
        )
        
        print(f"✅ New assistance session created: {session_id}")
        return chat_session
    
    def link_user_sessions(self, user):
        """
        Link all anonymous chat sessions to a user when they authenticate
        This should be called after user login/registration
        """
        try:
            # Find sessions with matching email
            sessions_to_link = AssistanceChat.objects.filter(
                models.Q(email=user.email) | 
                models.Q(anonymous_token__isnull=False, user__isnull=True)
            ).exclude(user=user)
            
            linked_count = 0
            for session in sessions_to_link:
                # Check if session email matches user email
                if session.email and session.email.lower() == user.email.lower():
                    session.user = user
                    session.linked_at = timezone.now()
                    session.save()
                    linked_count += 1
                    print(f"🔗 Linked session {session.session_id} to user {user.email}")
            
            # Also check sessions from same IP (optional, can be commented out for privacy)
            # ip_sessions = AssistanceChat.objects.filter(
            #     ip_address=user.last_login_ip,  # You'd need to track this
            #     user__isnull=True
            # ).exclude(email__isnull=False)
            # ... similar linking logic
            
            print(f"✅ Linked {linked_count} chat sessions to user {user.email}")
            return linked_count
            
        except Exception as e:
            print(f"❌ Error linking user sessions: {e}")
            return 0
    
    def get_user_chats(self, user):
        """
        Get all chat sessions for a user (including linked anonymous sessions)
        """
        # Get chats where user is owner
        user_chats = AssistanceChat.objects.filter(user=user)
        
        # Also get chats with matching email (even if not linked yet)
        email_chats = AssistanceChat.objects.filter(
            email__iexact=user.email,
            user__isnull=True
        )
        
        # Combine and deduplicate
        all_chats = list(user_chats) + list(email_chats)
        unique_chats = []
        seen_ids = set()
        
        for chat in all_chats:
            if chat.id not in seen_ids:
                seen_ids.add(chat.id)
                unique_chats.append(chat)
        
        # Sort by created date (newest first)
        unique_chats.sort(key=lambda x: x.created_at, reverse=True)
        
        return unique_chats
    # ============ QUESTION PROCESSING ============
    
    def process_question(self, chat_session, question):
        """Process user question with FAQ tracking and intelligent routing"""
        try:
            start_time = time.time()
            
            # Save user question
            user_message = AssistanceMessage.objects.create(
                chat=chat_session,
                message_type='user_question',
                content=question,
                sender=chat_session.user
            )
            
            # Track question frequency
            self._track_question_frequency(question, chat_session)
            
            # Check for exact FAQ matches first
            faq_match = self._find_exact_faq_match(question)
            
            if faq_match:
                # FAQ found - use it directly
                result = self._handle_faq_response(question, chat_session, faq_match)
            else:
                # No exact FAQ match, use AI
                result = self._handle_ai_response(question, chat_session)
            
            # Calculate response time
            response_time = time.time() - start_time
            
            # Log the interaction
            self._log_ai_response(chat_session, question, result, response_time)
            
            # Handle low confidence responses
            if result['confidence'] < self.confidence_threshold:
                result = self._handle_low_confidence(chat_session, result)
            
            return result
            
        except Exception as e:
            print(f"❌ Error processing question: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                'response': "I apologize, but I encountered an error processing your question. Please provide your email address for assistance from our team.",
                'requires_email': True,
                'confidence': 0.1,
                'escalated': False,
                'faq_id': None,
                'source': 'error'
            }
    
    def _track_question_frequency(self, question, chat_session):
        """Track how many times this question has been asked"""
        try:
            # Clean and normalize question
            cleaned_question = self._clean_question(question)
            
            # Find similar existing questions in the last 30 days
            cutoff_date = timezone.now() - timedelta(days=30)
            
            similar_questions = AssistanceMessage.objects.filter(
                message_type='user_question',
                created_at__gte=cutoff_date
            ).exclude(chat=chat_session)  # Exclude current chat
            
            if similar_questions.exists():
                # Calculate similarity with existing questions
                questions_texts = [cleaned_question]
                existing_questions = []
                
                for msg in similar_questions:
                    cleaned_existing = self._clean_question(msg.content)
                    questions_texts.append(cleaned_existing)
                    existing_questions.append(msg)
                
                # Calculate similarity
                try:
                    vectorizer = TfidfVectorizer().fit_transform(questions_texts)
                    vectors = vectorizer.toarray()
                    
                    current_vector = vectors[0]
                    existing_vectors = vectors[1:]
                    
                    similarities = cosine_similarity([current_vector], existing_vectors)[0]
                    
                    # Find similar questions (above threshold)
                    for i, similarity in enumerate(similarities):
                        if similarity >= self.similarity_threshold:
                            # This question has been asked before
                            # You could increment a counter or log this information
                            print(f"📊 Similar question found (similarity: {similarity:.2f})")
                            break
                except:
                    pass  # Skip similarity calculation if it fails
            
            # Check if question matches any FAQ
            matching_faqs = self._find_similar_faqs(question)
            for faq in matching_faqs:
                faq.increment_times_asked()
                print(f"📈 FAQ '{faq.id}' increment: now asked {faq.times_asked} times")
                
        except Exception as e:
            print(f"⚠️ Error tracking question frequency: {e}")
    
    def _clean_question(self, question):
        """Clean and normalize question text for comparison"""
        if not question:
            return ""
        
        # Convert to lowercase
        cleaned = question.lower()
        
        # Remove extra whitespace
        cleaned = ' '.join(cleaned.split())
        
        # Remove punctuation (optional, can be adjusted)
        import string
        cleaned = cleaned.translate(str.maketrans('', '', string.punctuation))
        
        return cleaned
    
    # ============ FAQ MATCHING ============
    
    def _find_exact_faq_match(self, question):
        """Find exact FAQ match for the question"""
        try:
            # Refresh FAQ cache if needed
            self._refresh_faq_cache()
            
            if not self.faq_cache:
                return None
            
            cleaned_question = self._clean_question(question)
            
            # First, check keywords
            for faq in self.faq_cache:
                if faq.keywords:
                    keywords = [k.strip().lower() for k in faq.keywords.split(',')]
                    # Check if any keyword is in the question
                    if any(keyword in cleaned_question for keyword in keywords):
                        return faq
            
            # Then check question similarity
            matching_faqs = self._find_similar_faqs(question)
            if matching_faqs:
                # Return the most similar FAQ
                return matching_faqs[0]
            
            return None
            
        except Exception as e:
            print(f"⚠️ Error finding FAQ match: {e}")
            return None
    
    def _find_similar_faqs(self, question, threshold=None):
        """Find FAQs similar to the question using cosine similarity"""
        if threshold is None:
            threshold = self.similarity_threshold
        
        try:
            self._refresh_faq_cache()
            
            if not self.faq_cache:
                return []
            
            # Prepare texts for similarity comparison
            question_text = self._clean_question(question)
            texts = [question_text]
            
            faq_data = []
            for faq in self.faq_cache:
                # Combine question and keywords for better matching
                combined_text = f"{self._clean_question(faq.question)} {faq.keywords or ''}"
                texts.append(combined_text)
                faq_data.append(faq)
            
            # Calculate similarity
            vectorizer = TfidfVectorizer().fit_transform(texts)
            vectors = vectorizer.toarray()
            
            question_vector = vectors[0]
            faq_vectors = vectors[1:]
            
            similarities = cosine_similarity([question_vector], faq_vectors)[0]
            
            # Find FAQs with similarity above threshold
            similar_faqs = []
            for i, similarity in enumerate(similarities):
                if similarity >= threshold:
                    similar_faqs.append({
                        'faq': faq_data[i],
                        'similarity': similarity
                    })
            
            # Sort by similarity (highest first)
            similar_faqs.sort(key=lambda x: x['similarity'], reverse=True)
            
            # Return only FAQ objects
            return [item['faq'] for item in similar_faqs]
            
        except Exception as e:
            print(f"⚠️ Error finding similar FAQs: {e}")
            return []
    
    def _refresh_faq_cache(self):
        """Refresh FAQ cache if it's stale"""
        cache_duration = 300  # 5 minutes in seconds
        
        if (not self.faq_cache or 
            not self.faq_last_update or 
            (timezone.now() - self.faq_last_update).seconds > cache_duration):
            
            self.faq_cache = list(FAQ.objects.filter(is_active=True))
            self.faq_last_update = timezone.now()
            print(f"🔄 FAQ cache refreshed: {len(self.faq_cache)} FAQs")
    
    # ============ RESPONSE HANDLERS ============
    
    def _handle_faq_response(self, question, chat_session, faq_match):
        """Handle response when FAQ is found"""
        # Increment FAQ usage count
        faq_match.increment_times_asked()
        
        # Save FAQ response
        AssistanceMessage.objects.create(
            chat=chat_session,
            message_type='ai_response',
            content=faq_match.answer,
            ai_model='faq-match',
            ai_response_quality=95  # High confidence for FAQ matches
        )
        
        return {
            'response': faq_match.answer,
            'requires_email': False,
            'confidence': 0.95,
            'faq_id': faq_match.id,
            'source': 'faq',
            'escalated': False
        }
    
    def _handle_ai_response(self, question, chat_session):
        """Handle response using AI service"""
        # Get chat history for context
        chat_history = list(chat_session.messages.values(
            'message_type', 'content'
        ).order_by('created_at'))
        
        # Get AI response
        ai_result = self.ai_service.generate_response(question, chat_history)
        
        # Save AI response
        AssistanceMessage.objects.create(
            chat=chat_session,
            message_type='ai_response',
            content=ai_result['response'],
            ai_model=ai_result.get('model', 'free-local-model'),
            ai_response_quality=int(ai_result['confidence'] * 100)
        )
        
        return {
            'response': ai_result['response'],
            'requires_email': False,
            'confidence': ai_result['confidence'],
            'faq_id': ai_result.get('faq_id'),
            'source': ai_result.get('source', 'free-ai'),
            'escalated': False
        }
    
    def _handle_low_confidence(self, chat_session, result):
        """Handle low confidence AI responses"""
        confidence = result['confidence']
        
        if confidence < 0.2:
            # Very low confidence - always escalate
            return self._escalate_due_to_low_confidence(chat_session, result)
        elif confidence < self.confidence_threshold:
            # Moderate low confidence - check for email
            if not chat_session.email and not chat_session.user:
                # No email available - ask for it
                chat_session.status = 'human_requested'
                chat_session.save()
                
                AssistanceMessage.objects.create(
                    chat=chat_session,
                    message_type='system',
                    content="System: AI confidence is low. Requested user email for human assistance."
                )
                
                result['requires_email'] = True
                return result
            else:
                # Email available, escalate
                return self._escalate_due_to_low_confidence(chat_session, result)
        
        return result
    
    def _escalate_due_to_low_confidence(self, chat_session, result):
        """Escalate chat due to low AI confidence"""
        chat_session.status = 'escalated'
        chat_session.save()
        
        # Send notification email if email exists
        if chat_session.email or chat_session.user:
            notification = "Your question requires human assistance. Our support team will contact you shortly."
            self.email_service.send_assistance_response(chat_session, notification, None)
            
            result['response'] = "Your question has been escalated to our support team. You'll receive an email response shortly."
            result['escalated'] = True
        
        AssistanceMessage.objects.create(
            chat=chat_session,
            message_type='system',
            content=f"System: Chat escalated due to low AI confidence ({result['confidence']:.2f})"
        )
        
        result['requires_email'] = False
        result['escalated'] = True
        return result
    
    # ============ LOGGING ============
    
    def _log_ai_response(self, chat_session, question, result, response_time):
        """Log AI response for analytics"""
        try:
            AIResponseLog.objects.create(
                chat=chat_session,
                user_query=question,
                ai_response=result['response'][:500],  # Limit response length
                model_used=result.get('source', 'unknown'),
                confidence_score=result['confidence'],
                response_time=response_time,
                faq_id=result.get('faq_id')
            )
        except Exception as e:
            print(f"⚠️ Error logging AI response: {e}")
    
    # ============ ESCALATION & HUMAN RESPONSE ============
    
    def escalate_to_human(self, chat_session, admin_user=None, reason="manual"):
        """Escalate chat to human support"""
        old_status = chat_session.status
        chat_session.status = 'escalated'
        
        if admin_user:
            chat_session.escalated_to = admin_user
        
        chat_session.save()
        
        # Log escalation
        AssistanceMessage.objects.create(
            chat=chat_session,
            message_type='system',
            content=f"System: Chat escalated from '{old_status}' by {admin_user.full_name if admin_user else 'system'} (reason: {reason})",
            sender=admin_user
        )
        
        # Send notification email
        if chat_session.email or chat_session.user:
            notification = "Your assistance request has been escalated to our support team. A representative will contact you shortly."
            self.email_service.send_assistance_response(chat_session, notification, admin_user)
        
        print(f"📤 Chat {chat_session.session_id} escalated to human support")
        return chat_session
    
    def send_human_response(self, chat_session, response_content, responder):
        """Send human response and email"""
        try:
            # Save human response
            AssistanceMessage.objects.create(
                chat=chat_session,
                message_type='human_response',
                content=response_content,
                sender=responder
            )
            
            # Update chat status
            chat_session.status = 'resolved'
            chat_session.resolved_at = timezone.now()
            chat_session.save()
            
            # Send email if recipient exists
            if chat_session.email or chat_session.user:
                success = self.email_service.send_assistance_response(
                    chat_session, response_content, responder
                )
                
                if success:
                    print(f"📧 Response email sent for chat {chat_session.session_id}")
                else:
                    print(f"⚠️ Failed to send email for chat {chat_session.session_id}")
                
                return success
            
            return True  # Success even if no email (e.g., authenticated user)
            
        except Exception as e:
            print(f"❌ Error sending human response: {e}")
            return False
    
    # ============ ANALYTICS & REPORTING ============
    
    def get_popular_questions(self, days=7, limit=20):
        """Get most frequently asked questions"""
        from_date = timezone.now() - timedelta(days=days)
        
        # Get user questions from messages
        user_questions = AssistanceMessage.objects.filter(
            message_type='user_question',
            created_at__gte=from_date
        ).values('content').annotate(
            count=models.Count('id'),
            last_asked=models.Max('created_at')
        ).order_by('-count')[:limit]
        
        # Process and enrich with FAQ matches
        popular_questions = []
        for item in user_questions:
            question_text = item['content']
            similar_faqs = self._find_similar_faqs(question_text, threshold=0.5)
            
            popular_questions.append({
                'question': question_text,
                'count': item['count'],
                'last_asked': item['last_asked'],
                'similar_faqs': [
                    {
                        'id': faq.id,
                        'question': faq.question,
                        'times_asked': faq.times_asked,
                        'helpful_count': faq.helpful_count
                    } for faq in similar_faqs[:3]  # Limit to top 3 matches
                ]
            })
        
        return popular_questions
    
    def get_faq_effectiveness(self, days=30):
        """Get FAQ effectiveness metrics"""
        from_date = timezone.now() - timedelta(days=days)
        
        # Get all FAQs with their usage stats
        faqs = FAQ.objects.filter(is_active=True)
        
        faq_stats = []
        for faq in faqs:
            # Count how many times this FAQ was matched
            matched_questions = AssistanceMessage.objects.filter(
                message_type='user_question',
                created_at__gte=from_date
            )
            
            # This is a simplified version - in production you'd want to store FAQ matches
            # Consider adding a ForeignKey from AssistanceMessage to FAQ
            
            faq_stats.append({
                'id': faq.id,
                'question': faq.question,
                'times_asked': faq.times_asked,
                'helpful_count': faq.helpful_count,
                'not_helpful_count': faq.not_helpful_count,
                'helpful_rate': (faq.helpful_count / faq.times_asked * 100) if faq.times_asked > 0 else 0,
                'category': faq.category
            })
        
        return sorted(faq_stats, key=lambda x: x['times_asked'], reverse=True)
    
    def update_faq_feedback(self, faq_id, was_helpful):
        """Update FAQ based on user feedback"""
        try:
            faq = FAQ.objects.get(id=faq_id)
            
            if was_helpful:
                faq.helpful_count += 1
            else:
                faq.not_helpful_count += 1
            
            faq.save()
            return True
        except FAQ.DoesNotExist:
            return False
    
    # ============ UTILITY METHODS ============
    
    def _get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0]
        return request.META.get('REMOTE_ADDR')
    
    def check_system_health(self):
        """Check health of assistance system components"""
        health_report = {
            'faq_count': FAQ.objects.filter(is_active=True).count(),
            'active_chats': AssistanceChat.objects.filter(is_active=True).count(),
            'escalated_chats': AssistanceChat.objects.filter(status='escalated').count(),
            'ai_service': self.ai_service.check_health() if hasattr(self.ai_service, 'check_health') else 'unknown',
            'email_service': self.email_service.check_health() if hasattr(self.email_service, 'check_health') else 'unknown',
            'faq_cache_size': len(self.faq_cache) if self.faq_cache else 0,
            'cache_age': (timezone.now() - self.faq_last_update).seconds if self.faq_last_update else 'never'
        }
        
        return health_report
    
    def suggest_new_faqs(self, min_occurrences=3):
        """Suggest new FAQs based on frequently asked questions"""
        popular_questions = self.get_popular_questions(days=30, limit=50)
        
        suggestions = []
        for pq in popular_questions:
            # Check if this question occurs frequently enough
            if pq['count'] >= min_occurrences:
                # Check if it already has a similar FAQ
                if not pq['similar_faqs']:
                    suggestions.append({
                        'question': pq['question'],
                        'occurrences': pq['count'],
                        'last_asked': pq['last_asked'],
                        'suggested_answer': None  # Could be generated by AI
                    })
        
        return suggestions
    
    def batch_update_faq_usage(self):
        """Batch update FAQ usage statistics from chat history"""
        print("🔄 Starting batch update of FAQ usage...")
        
        # This would typically run as a scheduled task
        # to update FAQ usage counts from historical data
        
        updated_count = 0
        for faq in FAQ.objects.filter(is_active=True):
            # Find messages that might match this FAQ
            # (This is a simplified version - in production you'd want a more robust matching)
            similar_questions = AssistanceMessage.objects.filter(
                message_type='user_question'
            )
            
            # This is where you'd implement your matching logic
            # and update faq.times_asked accordingly
            
            # For now, we'll just mark that we processed it
            updated_count += 1
        
        print(f"✅ Batch update completed: processed {updated_count} FAQs")
        return updated_count